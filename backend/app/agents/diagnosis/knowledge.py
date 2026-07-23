from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents.diagnosis.types import EvidenceItem
from app.core.config import Settings, get_settings


def load_knowledge_snapshot(db: Session) -> dict[str, Any]:
    """Return the immutable RAG publication and Aura KG scope for one run.

    RAG evidence is versioned through the management publication pipeline.
    The supplied Aura disease graph predates that pipeline and remains a
    first-class KG source even while no document-derived RAG version exists.
    """

    settings = get_settings()

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return _empty_snapshot("当前数据库不是 PostgreSQL，无法读取管理端发布清单", settings=settings)
    try:
        relation = db.scalar(text("SELECT to_regclass('admin.knowledge_publications')"))
        if relation is None:
            return _empty_snapshot("管理端知识发布表尚未创建", settings=settings)
        rows = db.execute(
            text(
                """
                SELECT DISTINCT ON (source.id)
                    publication.id::text AS publication_id,
                    publication.version AS publication_version,
                    publication.qdrant_collection,
                    publication.opensearch_index,
                    publication.neo4j_database,
                    publication.published_at,
                    source.id::text AS source_id,
                    source.title AS source_title,
                    source.source_url,
                    source_version.id::text AS source_version_id,
                    source_version.version AS source_version
                FROM admin.knowledge_publications AS publication
                JOIN admin.knowledge_build_runs AS build_run
                  ON build_run.id = publication.build_run_id
                JOIN admin.knowledge_source_versions AS source_version
                  ON source_version.id = build_run.source_version_id
                JOIN admin.knowledge_sources AS source
                  ON source.id = source_version.source_id
                WHERE publication.status = 'published'
                  AND build_run.status = 'succeeded'
                  AND source.status = 'ready'
                  AND source.published_version_id = source_version.id
                ORDER BY source.id, publication.published_at DESC NULLS LAST, publication.created_at DESC
                """
            )
        ).mappings().all()
    except Exception as error:
        # Snapshot discovery is read-only. A missing admin schema must not make
        # the diagnosis transaction unusable.
        db.rollback()
        return _empty_snapshot(f"读取知识发布快照失败：{error.__class__.__name__}", settings=settings)

    publications = [
        {
            "publication_id": row["publication_id"],
            "publication_version": row["publication_version"],
            "published_at": row["published_at"].isoformat() if row["published_at"] else None,
            "qdrant_collection": row["qdrant_collection"],
            "opensearch_index": row["opensearch_index"],
            "neo4j_database": row["neo4j_database"],
            "source_id": row["source_id"],
            "source_title": row["source_title"],
            "source_url": row["source_url"],
            "source_version_id": row["source_version_id"],
            "source_version": row["source_version"],
        }
        for row in rows
    ]
    publication_ids = [row["publication_id"] for row in publications]
    rag_available = bool(publications)
    kg_available, kg_reason = _aura_kg_status(settings)
    return {
        # ``available`` remains a top-level capability flag for callers that
        # only need to know whether either knowledge channel can contribute.
        "available": rag_available or kg_available,
        "reason": None if rag_available or kg_available else "尚无处于当前版本的已发布知识",
        "rag_available": rag_available,
        "rag_reason": None if rag_available else "尚无处于当前版本的已发布 RAG 文档知识",
        "kg_available": kg_available,
        "kg_reason": kg_reason,
        "kg_mode": "aura_curated" if kg_available else "unavailable",
        "kg_source_title": "Neo4j Aura 家蚕疾病知识图谱" if kg_available else None,
        "publication_ids": publication_ids,
        "qdrant_collections": _unique(row["qdrant_collection"] for row in publications),
        "opensearch_indexes": _unique(row["opensearch_index"] for row in publications),
        # User-side graph operations are intentionally pinned to the configured
        # Aura database, never to a database name carried by a build record.
        "neo4j_databases": [settings.neo4j_database] if kg_available else [],
        "publications": publications,
        "source_count": len(publications),
    }


class HNSWRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(
        self,
        *,
        vector: list[float],
        snapshot: dict[str, Any],
        limit: int,
    ) -> list[EvidenceItem]:
        from qdrant_client import QdrantClient, models

        publication_ids = list(snapshot.get("publication_ids", []))
        if not publication_ids:
            return []
        collections = list(snapshot.get("qdrant_collections", [])) or [self.settings.qdrant_collection]
        client = QdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
            timeout=30,
            trust_env=False,
        )
        source_map = _publication_source_map(snapshot)
        results: list[EvidenceItem] = []
        query_filter = models.Filter(
            must=[models.FieldCondition(key="publication_id", match=models.MatchAny(any=publication_ids))]
        )
        try:
            for collection in collections:
                response = client.query_points(
                    collection_name=collection,
                    query=vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
                for point in response.points:
                    payload = dict(point.payload or {})
                    publication_id = str(payload.get("publication_id", ""))
                    source = source_map.get(publication_id, {})
                    results.append(
                        _qa_evidence(
                            retriever="hnsw",
                            document_id=str(point.id),
                            score=float(point.score),
                            payload=payload,
                            source=source,
                        )
                    )
        finally:
            client.close()
        return sorted(results, key=lambda item: item.score or 0.0, reverse=True)[:limit]


class DomainTokenizer:
    def __init__(self) -> None:
        import jieba

        self.tokenizer = jieba.Tokenizer()
        dictionary_path = Path(__file__).resolve().parents[3] / "docs" / "knowledge" / "jieba_silkworm_userdict.txt"
        if dictionary_path.is_file():
            self.tokenizer.load_userdict(str(dictionary_path))

    def tokenize(self, value: str) -> str:
        return " ".join(token.strip() for token in self.tokenizer.cut(value, HMM=False) if token.strip())


class BM25Retriever:
    def __init__(self, settings: Settings, tokenizer: DomainTokenizer | None = None) -> None:
        self.settings = settings
        self.tokenizer = tokenizer or DomainTokenizer()

    def _client(self):
        from opensearchpy import OpenSearch

        parsed = urlparse(self.settings.opensearch_url)
        auth = None
        if self.settings.opensearch_username:
            auth = (self.settings.opensearch_username, self.settings.opensearch_password or "")
        return OpenSearch(
            hosts=[
                {
                    "host": parsed.hostname or "127.0.0.1",
                    "port": parsed.port or (443 if parsed.scheme == "https" else 9200),
                }
            ],
            http_auth=auth,
            use_ssl=parsed.scheme == "https",
            verify_certs=parsed.scheme == "https",
            timeout=30,
        )

    def search(self, *, query: str, snapshot: dict[str, Any], limit: int) -> list[EvidenceItem]:
        publication_ids = list(snapshot.get("publication_ids", []))
        if not publication_ids:
            return []
        indexes = list(snapshot.get("opensearch_indexes", [])) or [self.settings.opensearch_index]
        source_map = _publication_source_map(snapshot)
        tokenized = self.tokenizer.tokenize(query)
        should: list[dict[str, Any]] = [
            {"match_phrase": {"question": {"query": query, "boost": 4.0}}},
            {"match": {"question": {"query": query, "operator": "or", "boost": 2.0}}},
        ]
        if tokenized:
            should.append(
                {
                    "match": {
                        "question_tokens": {
                            "query": tokenized,
                            "operator": "or",
                            "minimum_should_match": "35%",
                            "boost": 3.0,
                        }
                    }
                }
            )
        client = self._client()
        try:
            response = client.search(
                index=",".join(indexes),
                body={
                    "size": limit,
                    "track_total_hits": False,
                    "query": {
                        "bool": {
                            "filter": [{"terms": {"publication_id": publication_ids}}],
                            "should": should,
                            "minimum_should_match": 1,
                        }
                    },
                },
            )
        finally:
            client.close()
        rows = response.get("hits", {}).get("hits", [])
        results: list[EvidenceItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            payload = dict(row.get("_source") or {})
            publication_id = str(payload.get("publication_id", ""))
            results.append(
                _qa_evidence(
                    retriever="bm25",
                    document_id=str(row.get("_id", "")),
                    score=float(row.get("_score") or 0.0),
                    payload=payload,
                    source=source_map.get(publication_id, {}),
                )
            )
        return results


class KGRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(
        self,
        *,
        terms: list[str],
        snapshot: dict[str, Any],
        limit: int,
        anchors: list[str] | None = None,
    ) -> list[EvidenceItem]:
        from neo4j import GraphDatabase

        publication_ids = list(snapshot.get("publication_ids", []))
        cleaned_terms = _graph_terms([*(anchors or []), *terms])
        # Older persisted runs do not have the channel-specific fields. They
        # retain the former publication-scoped behavior for replay safety.
        kg_available = bool(snapshot.get("kg_available")) if "kg_available" in snapshot else bool(publication_ids)
        if not kg_available or not cleaned_terms:
            return []
        self.settings.require_neo4j_aura()
        database = self.settings.neo4j_database
        cypher = """
            MATCH (subject)-[relation]->(object)
            WHERE (coalesce(relation.publication_id, '') = ''
                   OR relation.publication_id IN $publication_ids)
              AND any(term IN $terms WHERE
                    toLower(coalesce(subject.name, '')) CONTAINS toLower(term)
                 OR toLower(term) CONTAINS toLower(coalesce(subject.name, ''))
                 OR toLower(coalesce(object.name, '')) CONTAINS toLower(term)
                 OR toLower(term) CONTAINS toLower(coalesce(object.name, ''))
                 OR any(alias IN coalesce(subject.aliases, []) WHERE toLower(alias) CONTAINS toLower(term))
                 OR any(alias IN coalesce(object.aliases, []) WHERE toLower(alias) CONTAINS toLower(term)))
            RETURN subject.name AS subject_name,
                   labels(subject) AS subject_labels,
                   type(relation) AS relation_type,
                   object.name AS object_name,
                   labels(object) AS object_labels,
                   coalesce(relation.latest_evidence, relation.evidence, '') AS evidence,
                   coalesce(relation.latest_provenance, properties(relation)['provenance'], '') AS provenance,
                   coalesce(relation.source_docs, []) AS source_documents,
                   relation.confidence AS confidence,
                   coalesce(relation.publication_id, '') AS publication_id
            ORDER BY CASE WHEN subject.name IN $terms OR object.name IN $terms THEN 0 ELSE 1 END,
                     subject.name, relation_type, object.name
            LIMIT $limit
        """
        driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )
        try:
            driver.verify_connectivity()
            session_kwargs = {"database": database} if database else {}
            with driver.session(**session_kwargs) as session:
                rows = [
                    record.data()
                    for record in session.run(
                        cypher,
                        publication_ids=publication_ids,
                        terms=cleaned_terms,
                        limit=limit,
                    )
                ]
        finally:
            driver.close()
        source_map = _publication_source_map(snapshot)
        return [
            _graph_evidence(row, source_map=source_map, snapshot=snapshot, terms=cleaned_terms)
            for row in rows
        ]


def _qa_evidence(
    *,
    retriever: str,
    document_id: str,
    score: float,
    payload: dict[str, Any],
    source: dict[str, Any],
) -> EvidenceItem:
    question = " ".join(str(payload.get("question", "")).split())
    answer = str(payload.get("answer", "")).strip()
    evidence = str(payload.get("evidence", "")).strip()
    content_parts = []
    if answer:
        content_parts.append(f"知识回答：{answer}")
    if evidence and evidence not in answer:
        content_parts.append(f"原文依据：{evidence}")
    content = "\n".join(content_parts) or question
    heading = payload.get("heading_path")
    if isinstance(heading, list):
        source_page = " / ".join(str(value) for value in heading if str(value).strip()) or None
    else:
        source_page = str(heading).strip() or None
    return EvidenceItem(
        evidence_key=f"rag:{document_id}",
        evidence_type="rag_document",
        retriever=retriever,
        title=question or "知识库问答",
        content=content[:8000],
        source_name=str(payload.get("source_title") or source.get("source_title") or "知识库文档"),
        source_uri=source.get("source_url"),
        source_version=str(payload.get("source_version") or source.get("source_version") or "") or None,
        source_page=source_page,
        score=score,
        metadata={
            "document_id": document_id,
            "chunk_id": payload.get("chunk_id"),
            "source_id": payload.get("source_id") or source.get("source_id"),
            "source_version_id": payload.get("source_version_id") or source.get("source_version_id"),
            "publication_id": payload.get("publication_id"),
            "keywords": payload.get("keywords") or [],
            "knowledge_types": payload.get("knowledge_types") or [],
            "channels": [retriever],
        },
    )


def _graph_evidence(
    row: dict[str, Any],
    *,
    source_map: dict[str, dict[str, Any]],
    snapshot: dict[str, Any],
    terms: list[str],
) -> EvidenceItem:
    subject = str(row.get("subject_name") or "未知实体")
    relation = str(row.get("relation_type") or "关联")
    object_name = str(row.get("object_name") or "未知实体")
    evidence = str(row.get("evidence") or "").strip()
    publication_id = str(row.get("publication_id") or "")
    provenance = _parse_provenance(row.get("provenance"))
    source = source_map.get(publication_id, {})
    raw_key = "\x1f".join([publication_id, subject, relation, object_name, json.dumps(provenance, sort_keys=True, default=str)])
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
    direct = subject in terms or object_name in terms
    content = f"{subject} —{relation}→ {object_name}"
    if evidence:
        content += f"。原文依据：{evidence}"
    heading = provenance.get("heading_path")
    source_page = " / ".join(str(value) for value in heading) if isinstance(heading, list) else None
    return EvidenceItem(
        evidence_key=f"kg:{digest}",
        evidence_type="kg_path",
        retriever="kg",
        title=f"{subject} · {relation} · {object_name}",
        content=content[:8000],
        source_name=str(
            provenance.get("source_title")
            or source.get("source_title")
            or snapshot.get("kg_source_title")
            or "知识图谱"
        ),
        source_uri=source.get("source_url"),
        source_version=str(provenance.get("source_version") or source.get("source_version") or "") or None,
        source_page=source_page,
        score=1.0 if direct else 0.82,
        metadata={
            "publication_id": publication_id,
            "source_id": provenance.get("source_id") or source.get("source_id"),
            "source_version_id": provenance.get("source_version_id") or source.get("source_version_id"),
            "chunk_id": provenance.get("chunk_id"),
            "subject": subject,
            "subject_labels": row.get("subject_labels") or [],
            "relation": relation,
            "object": object_name,
            "object_labels": row.get("object_labels") or [],
            "source_documents": row.get("source_documents") or [],
            "confidence": row.get("confidence"),
            "graph_source": snapshot.get("kg_mode") or ("published" if publication_id else "curated"),
            "channels": ["kg"],
        },
    )


def _parse_provenance(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _publication_source_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("publication_id")): row
        for row in snapshot.get("publications", [])
        if isinstance(row, dict) and row.get("publication_id")
    }


def _graph_terms(values: list[str]) -> list[str]:
    generic = {"家蚕", "蚕", "问题", "诊断", "知识", "疾病", "怎么回事", "怎么办"}
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())[:80]
        if len(normalized) < 2 or normalized in generic or normalized in result:
            continue
        result.append(normalized)
        if len(result) >= 12:
            break
    return result


def _unique(values) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _aura_kg_status(settings: Settings) -> tuple[bool, str | None]:
    try:
        settings.require_neo4j_aura()
    except RuntimeError as error:
        return False, str(error)
    return True, None


def _empty_snapshot(reason: str, *, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    kg_available, kg_reason = _aura_kg_status(settings)
    return {
        "available": kg_available,
        "reason": None if kg_available else reason,
        "rag_available": False,
        "rag_reason": reason,
        "kg_available": kg_available,
        "kg_reason": kg_reason,
        "kg_mode": "aura_curated" if kg_available else "unavailable",
        "kg_source_title": "Neo4j Aura 家蚕疾病知识图谱" if kg_available else None,
        "publication_ids": [],
        "qdrant_collections": [],
        "opensearch_indexes": [],
        "neo4j_databases": [settings.neo4j_database] if kg_available else [],
        "publications": [],
        "source_count": 0,
    }

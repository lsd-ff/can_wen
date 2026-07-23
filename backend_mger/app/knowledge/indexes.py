from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import Settings, get_settings
from app.knowledge.schema import (
    KG_NEO4J_LABELS,
    KG_NEO4J_RELATION_TYPES,
    KG_RELATIONS,
    KG_SCHEMA_LABELS,
)


def _cypher_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def _stable_graph_node_id(label: str, name: str) -> str:
    digest = hashlib.sha256(f"{label}\x1f{name}".encode("utf-8")).hexdigest()[:20]
    return f"AUTO_{label}_{digest}"


def _json_safe_properties(value: Any) -> dict[str, Any]:
    """Convert Neo4j temporal/spatial values without leaking driver objects."""

    return json.loads(json.dumps(dict(value or {}), ensure_ascii=False, default=str))


class QdrantQAIndex:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _client(self):
        from qdrant_client import QdrantClient

        return QdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
            timeout=30,
            trust_env=False,
        )

    def ensure_collection(self) -> None:
        from qdrant_client import models

        client = self._client()
        if not client.collection_exists(self.settings.qdrant_collection):
            client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=self.settings.embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

    def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        from qdrant_client import models

        if len(vector) != self.settings.embedding_dimensions:
            raise ValueError("Qdrant 向量维度与配置不一致")
        self.ensure_collection()
        self._client().upsert(
            collection_name=self.settings.qdrant_collection,
            wait=True,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    def delete(self, point_ids: list[str]) -> None:
        from qdrant_client import models

        if not point_ids:
            return
        client = self._client()
        if not client.collection_exists(self.settings.qdrant_collection):
            return
        client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=models.PointIdsList(points=point_ids),
            wait=True,
        )


class DomainTokenizer:
    def __init__(self, dictionary_path: Path | None = None) -> None:
        import jieba

        self.tokenizer = jieba.Tokenizer()
        path = dictionary_path or (
            Path(__file__).resolve().parents[3] / "backend" / "docs" / "knowledge" / "jieba_silkworm_userdict.txt"
        )
        if path.is_file():
            self.tokenizer.load_userdict(str(path))

    def tokenize(self, text: str) -> str:
        return " ".join(token.strip() for token in self.tokenizer.cut(text, HMM=False) if token.strip())


class OpenSearchQAIndex:
    def __init__(self, settings: Settings | None = None, tokenizer: DomainTokenizer | None = None) -> None:
        self.settings = settings or get_settings()
        self.tokenizer = tokenizer or DomainTokenizer()

    def _client(self):
        from opensearchpy import OpenSearch

        parsed = urlparse(self.settings.opensearch_url)
        auth = None
        if self.settings.opensearch_username:
            auth = (self.settings.opensearch_username, self.settings.opensearch_password or "")
        return OpenSearch(
            hosts=[{"host": parsed.hostname or "127.0.0.1", "port": parsed.port or (443 if parsed.scheme == "https" else 9200)}],
            http_auth=auth,
            use_ssl=parsed.scheme == "https",
            verify_certs=parsed.scheme == "https",
            timeout=30,
        )

    def ensure_index(self) -> None:
        client = self._client()
        if client.indices.exists(index=self.settings.opensearch_index):
            return
        client.indices.create(
            index=self.settings.opensearch_index,
            body={
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "analysis": {"analyzer": {"space_analyzer": {"type": "custom", "tokenizer": "whitespace", "filter": ["lowercase"]}}},
                },
                "mappings": {
                    "dynamic": "strict",
                    "properties": {
                        "question": {"type": "text"},
                        "question_tokens": {"type": "text", "analyzer": "space_analyzer"},
                        "answer": {"type": "text", "index": False},
                        "evidence": {"type": "text", "index": False},
                        "keywords": {"type": "keyword"},
                        "knowledge_types": {"type": "keyword"},
                        "source_id": {"type": "keyword"},
                        "source_title": {"type": "keyword"},
                        "source_version_id": {"type": "keyword"},
                        "source_version": {"type": "keyword"},
                        "chunk_id": {"type": "keyword"},
                        "heading_path": {"type": "keyword"},
                        "publication_id": {"type": "keyword"},
                        "published_at": {"type": "date"},
                    },
                },
            },
        )

    def upsert(self, document_id: str, payload: dict[str, Any]) -> None:
        self.ensure_index()
        body = {**payload, "question_tokens": self.tokenizer.tokenize(str(payload["question"]))}
        self._client().index(index=self.settings.opensearch_index, id=document_id, body=body, refresh=False)

    def refresh(self) -> None:
        self._client().indices.refresh(index=self.settings.opensearch_index)

    def delete(self, document_id: str) -> None:
        self.delete_many([document_id])

    def delete_many(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        client = self._client()
        if not client.indices.exists(index=self.settings.opensearch_index):
            return
        for document_id in document_ids:
            client.delete(index=self.settings.opensearch_index, id=document_id, ignore=[404], refresh=False)
        client.indices.refresh(index=self.settings.opensearch_index)


class Neo4jKnowledgeGraph:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _driver(self):
        from neo4j import GraphDatabase

        self.settings.require_neo4j_aura()
        return GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )

    def ensure_schema(self) -> None:
        with self._driver() as driver:
            driver.verify_connectivity()
            with driver.session(database=self.settings.neo4j_database) as session:
                indexed_name_labels: set[str] = set()
                for record in session.run(
                    "SHOW INDEXES YIELD labelsOrTypes, properties "
                    "RETURN labelsOrTypes, properties"
                ):
                    labels = record.get("labelsOrTypes") or []
                    properties = record.get("properties") or []
                    if "name" in properties:
                        indexed_name_labels.update(str(label) for label in labels)
                for label in KG_SCHEMA_LABELS:
                    physical_name = KG_NEO4J_LABELS[label]
                    if physical_name in indexed_name_labels:
                        continue
                    physical_label = _cypher_identifier(KG_NEO4J_LABELS[label])
                    session.run(
                        f"CREATE INDEX kg_{label}_name_lookup IF NOT EXISTS "
                        f"FOR (n:{physical_label}) ON (n.name)"
                    ).consume()

    def upsert_triple(self, payload: dict[str, Any]) -> None:
        subject_type = str(payload["subject_type"])
        object_type = str(payload["object_type"])
        relation = str(payload["relation"])
        expected = KG_RELATIONS.get(relation)
        if subject_type not in KG_SCHEMA_LABELS or object_type not in KG_SCHEMA_LABELS or expected != (subject_type, object_type):
            raise ValueError("三元组类型不符合家蚕疾病 Schema")

        subject_label = _cypher_identifier(KG_NEO4J_LABELS[subject_type])
        object_label = _cypher_identifier(KG_NEO4J_LABELS[object_type])
        physical_relation = _cypher_identifier(KG_NEO4J_RELATION_TYPES[relation])

        cypher = f"""
        MERGE (s:{subject_label} {{name: $subject_name}})
        ON CREATE SET s.id = $subject_id, s.created_at = datetime(), s.aliases = []
        SET s.updated_at = datetime(),
            s.aliases = reduce(acc = coalesce(s.aliases, []), x IN $subject_aliases |
                CASE WHEN x IN acc THEN acc ELSE acc + x END)
        MERGE (o:{object_label} {{name: $object_name}})
        ON CREATE SET o.id = $object_id, o.created_at = datetime(), o.aliases = []
        SET o.updated_at = datetime(),
            o.aliases = reduce(acc = coalesce(o.aliases, []), x IN $object_aliases |
                CASE WHEN x IN acc THEN acc ELSE acc + x END)
        MERGE (s)-[r:{physical_relation}]->(o)
        ON CREATE SET r.created_at = datetime(), r.source_refs = [], r.canwen_managed = true
        SET r.updated_at = datetime(),
            r.source_refs = reduce(acc = coalesce(r.source_refs, []), x IN $source_refs |
                CASE WHEN x IN acc THEN acc ELSE acc + x END),
            r.latest_evidence = $latest_evidence,
            r.latest_provenance = $latest_provenance,
            r.publication_id = $publication_id
        """
        subject_surface = str(payload.get("subject_name", payload["subject_canonical_name"]))
        object_surface = str(payload.get("object_name", payload["object_canonical_name"]))
        source_ref = "|".join(
            [
                str(payload.get("source_version_id", "")),
                str(payload.get("chunk_id", "")),
                str(payload.get("evidence_sha256", "")),
            ]
        )
        parameters = {
            "subject_name": str(payload["subject_canonical_name"]),
            "subject_id": _stable_graph_node_id(subject_type, str(payload["subject_canonical_name"])),
            "subject_aliases": [] if subject_surface == payload["subject_canonical_name"] else [subject_surface],
            "object_name": str(payload["object_canonical_name"]),
            "object_id": _stable_graph_node_id(object_type, str(payload["object_canonical_name"])),
            "object_aliases": [] if object_surface == payload["object_canonical_name"] else [object_surface],
            "source_refs": [source_ref],
            "latest_evidence": str(payload.get("evidence", "")),
            "latest_provenance": json.dumps(payload.get("provenance", {}), ensure_ascii=False),
            "publication_id": str(payload.get("publication_id", "")),
        }
        with self._driver() as driver:
            with driver.session(database=self.settings.neo4j_database) as session:
                session.run(cypher, parameters).consume()

    def delete_source_artifacts(
        self,
        source_version_ids: list[str],
        publication_ids: list[str],
    ) -> dict[str, int]:
        """Remove only provenance owned by the deleted source.

        Relationships created by CanW are deleted when their final source reference
        disappears. Pre-existing Aura relationships are preserved even when CanW
        temporarily attached provenance to them.
        """

        version_ids = sorted(set(source_version_ids))
        if not version_ids:
            return {"relationships_deleted": 0, "relationships_updated": 0, "nodes_deleted": 0}
        parameters = {
            "source_version_ids": version_ids,
            "publication_ids": sorted(set(publication_ids)),
        }
        delete_relationships = """
        MATCH (s)-[r]->(o)
        WHERE coalesce(r.canwen_managed, false) = true
          AND size(coalesce(r.source_refs, [])) > 0
          AND all(ref IN coalesce(r.source_refs, [])
                  WHERE split(ref, '|')[0] IN $source_version_ids)
        WITH collect(r) AS doomed,
             collect(DISTINCT elementId(s)) + collect(DISTINCT elementId(o)) AS candidate_node_ids
        FOREACH (relationship IN doomed | DELETE relationship)
        RETURN size(doomed) AS deleted, candidate_node_ids
        """
        update_relationships = """
        MATCH ()-[r]->()
        WHERE any(ref IN coalesce(r.source_refs, [])
                  WHERE split(ref, '|')[0] IN $source_version_ids)
        SET r.source_refs = [ref IN coalesce(r.source_refs, [])
                             WHERE NOT (split(ref, '|')[0] IN $source_version_ids)],
            r.latest_evidence = CASE
                WHEN r.publication_id IN $publication_ids THEN null
                ELSE r.latest_evidence END,
            r.latest_provenance = CASE
                WHEN r.publication_id IN $publication_ids THEN null
                ELSE r.latest_provenance END,
            r.publication_id = CASE
                WHEN r.publication_id IN $publication_ids THEN null
                ELSE r.publication_id END,
            r.updated_at = datetime()
        RETURN count(r) AS updated
        """
        delete_orphan_nodes = """
        MATCH (n)
        WHERE elementId(n) IN $candidate_node_ids
          AND coalesce(n.id, '') STARTS WITH 'AUTO_'
          AND NOT EXISTS { MATCH (n)--() }
        WITH collect(n) AS doomed
        FOREACH (node IN doomed | DELETE node)
        RETURN size(doomed) AS deleted
        """
        with self._driver() as driver:
            with driver.session(database=self.settings.neo4j_database) as session:
                deleted_record = session.run(delete_relationships, **parameters).single()
                updated_record = session.run(update_relationships, **parameters).single()
                candidate_node_ids = list(deleted_record["candidate_node_ids"] if deleted_record else [])
                nodes_record = session.run(
                    delete_orphan_nodes,
                    candidate_node_ids=candidate_node_ids,
                ).single()
        return {
            "relationships_deleted": int(deleted_record["deleted"] if deleted_record else 0),
            "relationships_updated": int(updated_record["updated"] if updated_record else 0),
            "nodes_deleted": int(nodes_record["deleted"] if nodes_record else 0),
        }

    def preview(self, query: str = "", limit: int = 120) -> dict[str, list[dict[str, Any]]]:
        safe_limit = max(1, min(limit, 300))
        cypher = """
        MATCH (s)-[r]->(o)
        WHERE $search_text = ''
           OR toLower(s.name) CONTAINS toLower($search_text)
           OR toLower(o.name) CONTAINS toLower($search_text)
        RETURN elementId(s) AS source_id, labels(s)[0] AS source_type, s.name AS source_name,
               type(r) AS relation, elementId(r) AS relation_id,
               elementId(o) AS target_id, labels(o)[0] AS target_type, o.name AS target_name,
               properties(r)['latest_evidence'] AS evidence,
               properties(r)['latest_provenance'] AS provenance
        LIMIT $limit
        """
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        internal_labels = {physical: internal for internal, physical in KG_NEO4J_LABELS.items()}
        internal_relations = {physical: internal for internal, physical in KG_NEO4J_RELATION_TYPES.items()}
        with self._driver() as driver:
            with driver.session(database=self.settings.neo4j_database) as session:
                for record in session.run(cypher, search_text=query.strip(), limit=safe_limit):
                    source_id, target_id = record["source_id"], record["target_id"]
                    source_physical_type = str(record["source_type"])
                    target_physical_type = str(record["target_type"])
                    physical_relation = str(record["relation"])
                    nodes[source_id] = {
                        "id": source_id,
                        "type": internal_labels.get(source_physical_type, source_physical_type),
                        "type_label": source_physical_type,
                        "name": record["source_name"],
                    }
                    nodes[target_id] = {
                        "id": target_id,
                        "type": internal_labels.get(target_physical_type, target_physical_type),
                        "type_label": target_physical_type,
                        "name": record["target_name"],
                    }
                    edges.append(
                        {
                            "id": record["relation_id"],
                            "source": source_id,
                            "target": target_id,
                            "relation": KG_NEO4J_RELATION_TYPES.get(physical_relation, physical_relation),
                            "relation_key": internal_relations.get(physical_relation, physical_relation),
                            "evidence": record["evidence"],
                            "provenance": record["provenance"],
                        }
                    )
        return {"nodes": list(nodes.values()), "edges": edges}

    def explore(self, query: str = "", limit: int = 3000) -> dict[str, Any]:
        """Return a Neo4j Browser-style graph result and database schema summary.

        The compact ``preview`` endpoint remains available for older clients.
        This method is intended for the full graph workbench and therefore
        returns all relationships in the current Aura graph when they fit
        within the bounded result limit.
        """

        safe_limit = max(1, min(limit, 5000))
        search_text = query.strip()
        where_clause = """
        WHERE $search_text = ''
           OR toLower(coalesce(s.name, '')) CONTAINS toLower($search_text)
           OR toLower(coalesce(o.name, '')) CONTAINS toLower($search_text)
           OR any(alias IN coalesce(s.aliases, []) WHERE toLower(toString(alias)) CONTAINS toLower($search_text))
           OR any(alias IN coalesce(o.aliases, []) WHERE toLower(toString(alias)) CONTAINS toLower($search_text))
        """
        graph_cypher = f"""
        MATCH (s)-[r]->(o)
        {where_clause}
        WITH s, r, o ORDER BY elementId(r)
        LIMIT $limit
        RETURN elementId(s) AS source_id, labels(s)[0] AS source_type,
               coalesce(s.name, s.id, elementId(s)) AS source_name,
               type(r) AS relation, elementId(r) AS relation_id,
               elementId(o) AS target_id, labels(o)[0] AS target_type,
               coalesce(o.name, o.id, elementId(o)) AS target_name
        """
        count_cypher = f"""
        MATCH (s)-[r]->(o)
        {where_clause}
        RETURN count(r) AS count
        """
        internal_labels = {physical: internal for internal, physical in KG_NEO4J_LABELS.items()}
        internal_relations = {physical: internal for internal, physical in KG_NEO4J_RELATION_TYPES.items()}

        with self._driver() as driver:
            with driver.session(database=self.settings.neo4j_database) as session:
                graph_rows = list(
                    session.run(
                        graph_cypher,
                        search_text=search_text,
                        limit=safe_limit,
                    )
                )
                schema_record = session.run(
                    """
                    CALL () {
                      MATCH (n)
                      UNWIND labels(n) AS label
                      WITH label, count(*) AS count
                      ORDER BY count DESC, label
                      RETURN collect({label: label, count: count}) AS node_types
                    }
                    CALL () {
                      MATCH ()-[r]->()
                      WITH type(r) AS relation, count(*) AS count
                      ORDER BY count DESC, relation
                      RETURN collect({relation: relation, count: count}) AS relationship_types
                    }
                    CALL () {
                      CALL db.propertyKeys() YIELD propertyKey
                      WITH propertyKey ORDER BY propertyKey
                      RETURN collect(propertyKey) AS property_keys
                    }
                    RETURN node_types, relationship_types, property_keys
                    """
                ).single(strict=True)
                label_rows = list(schema_record["node_types"])
                relation_rows = list(schema_record["relationship_types"])
                property_keys = [str(key) for key in schema_record["property_keys"]]
                if search_text:
                    matching_relationships = int(
                        session.run(count_cypher, search_text=search_text).single(strict=True)["count"]
                    )
                else:
                    matching_relationships = sum(int(row["count"]) for row in relation_rows)

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        degree: dict[str, int] = {}
        for record in graph_rows:
            source_id, target_id = str(record["source_id"]), str(record["target_id"])
            source_physical_type = str(record["source_type"])
            target_physical_type = str(record["target_type"])
            physical_relation = str(record["relation"])
            nodes[source_id] = {
                "id": source_id,
                "type": internal_labels.get(source_physical_type, source_physical_type),
                "type_label": source_physical_type,
                "name": str(record["source_name"]),
            }
            nodes[target_id] = {
                "id": target_id,
                "type": internal_labels.get(target_physical_type, target_physical_type),
                "type_label": target_physical_type,
                "name": str(record["target_name"]),
            }
            degree[source_id] = degree.get(source_id, 0) + 1
            degree[target_id] = degree.get(target_id, 0) + 1
            edges.append(
                {
                    "id": str(record["relation_id"]),
                    "source": source_id,
                    "target": target_id,
                    "relation": physical_relation,
                    "relation_key": internal_relations.get(physical_relation, physical_relation),
                }
            )
        for node_id, node in nodes.items():
            node["degree"] = degree.get(node_id, 0)

        node_types = [
            {
                "key": internal_labels.get(str(row["label"]), str(row["label"])),
                "label": str(row["label"]),
                "count": int(row["count"]),
            }
            for row in label_rows
        ]
        relationship_types = [
            {
                "key": internal_relations.get(str(row["relation"]), str(row["relation"])),
                "label": str(row["relation"]),
                "count": int(row["count"]),
            }
            for row in relation_rows
        ]
        total_nodes = sum(item["count"] for item in node_types)
        total_relationships = sum(item["count"] for item in relationship_types)
        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "schema": {
                "total_nodes": total_nodes,
                "total_relationships": total_relationships,
                "node_types": node_types,
                "relationship_types": relationship_types,
                "property_keys": property_keys,
            },
            "result": {
                "node_count": len(nodes),
                "relationship_count": len(edges),
                "matching_relationships": matching_relationships,
                "limit": safe_limit,
                "truncated": matching_relationships > len(edges),
                "query": search_text,
            },
        }

    def detail(self, element_id: str, kind: str) -> dict[str, Any] | None:
        internal_labels = {physical: internal for internal, physical in KG_NEO4J_LABELS.items()}
        internal_relations = {physical: internal for internal, physical in KG_NEO4J_RELATION_TYPES.items()}
        with self._driver() as driver:
            with driver.session(database=self.settings.neo4j_database) as session:
                if kind == "node":
                    record = session.run(
                        """
                        MATCH (n) WHERE elementId(n) = $element_id
                        OPTIONAL MATCH (n)-[r]-()
                        RETURN elementId(n) AS id, labels(n)[0] AS type,
                               coalesce(n.name, n.id, elementId(n)) AS name,
                               properties(n) AS properties, count(r) AS degree
                        """,
                        element_id=element_id,
                    ).single()
                    if record is None:
                        return None
                    physical_type = str(record["type"])
                    return {
                        "kind": "node",
                        "node": {
                            "id": str(record["id"]),
                            "type": internal_labels.get(physical_type, physical_type),
                            "type_label": physical_type,
                            "name": str(record["name"]),
                            "degree": int(record["degree"]),
                            "properties": _json_safe_properties(record["properties"]),
                        },
                    }
                if kind != "relationship":
                    raise ValueError("不支持的图谱元素类型")
                record = session.run(
                    """
                    MATCH (s)-[r]->(o) WHERE elementId(r) = $element_id
                    RETURN elementId(r) AS id, type(r) AS relation,
                           properties(r) AS properties,
                           elementId(s) AS source_id, coalesce(s.name, s.id, elementId(s)) AS source_name,
                           elementId(o) AS target_id, coalesce(o.name, o.id, elementId(o)) AS target_name
                    """,
                    element_id=element_id,
                ).single()
                if record is None:
                    return None
                physical_relation = str(record["relation"])
                properties = _json_safe_properties(record["properties"])
                return {
                    "kind": "relationship",
                    "relationship": {
                        "id": str(record["id"]),
                        "source": str(record["source_id"]),
                        "source_name": str(record["source_name"]),
                        "target": str(record["target_id"]),
                        "target_name": str(record["target_name"]),
                        "relation": physical_relation,
                        "relation_key": internal_relations.get(physical_relation, physical_relation),
                        "properties": properties,
                        "evidence": properties.get("latest_evidence"),
                        "provenance": properties.get("latest_provenance"),
                    },
                }

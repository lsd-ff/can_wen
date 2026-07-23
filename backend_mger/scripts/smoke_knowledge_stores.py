"""Run an isolated write/read/cleanup smoke test for knowledge infrastructure."""

from __future__ import annotations

import uuid
from contextlib import suppress

from redis import Redis

from app.config import Settings
from app.knowledge.indexes import Neo4jKnowledgeGraph, OpenSearchQAIndex, QdrantQAIndex


def main() -> None:
    marker = uuid.uuid4().hex[:12]
    point_id = str(uuid.uuid4())
    disease_name = f"__canw_smoke_disease_{marker}"
    symptom_name = f"__canw_smoke_symptom_{marker}"
    settings = Settings(
        qdrant_collection=f"silkworm_smoke_{marker}",
        opensearch_index=f"silkworm-smoke-{marker}",
    )
    qdrant = QdrantQAIndex(settings)
    opensearch = OpenSearchQAIndex(settings)
    neo4j = Neo4jKnowledgeGraph(settings)

    qdrant_client = None
    opensearch_client = None
    try:
        redis_ok = bool(Redis.from_url(settings.redis_url, socket_timeout=5).ping())

        vector = [0.0] * settings.embedding_dimensions
        vector[0] = 1.0
        qa_payload = {
            "question": "家蚕核型多角体病有哪些症状？",
            "answer": "病蚕可出现体躯肿胀等症状。",
            "evidence": "病蚕常表现为体躯肿胀。",
            "keywords": ["家蚕核型多角体病", "体躯肿胀"],
            "knowledge_types": ["symptom"],
            "source_id": marker,
            "source_title": "基础设施隔离测试",
            "source_version_id": marker,
            "source_version": "smoke",
            "chunk_id": marker,
            "heading_path": ["基础设施隔离测试"],
            "publication_id": marker,
            "published_at": "2026-07-20T00:00:00+00:00",
        }
        qdrant.upsert(point_id, vector, qa_payload)
        qdrant_client = qdrant._client()
        qdrant_ok = len(
            qdrant_client.retrieve(
                collection_name=settings.qdrant_collection,
                ids=[point_id],
                with_payload=True,
            )
        ) == 1

        opensearch.upsert(point_id, qa_payload)
        opensearch.refresh()
        opensearch_client = opensearch._client()
        search_result = opensearch_client.search(
            index=settings.opensearch_index,
            body={
                "query": {
                    "match": {
                        "question_tokens": opensearch.tokenizer.tokenize("核型多角体病症状")
                    }
                }
            },
        )
        opensearch_ok = int(search_result["hits"]["total"]["value"]) >= 1

        neo4j.ensure_schema()
        neo4j.upsert_triple(
            {
                "subject_name": disease_name,
                "subject_type": "Disease",
                "subject_canonical_name": disease_name,
                "relation": "HAS_SYMPTOM",
                "object_name": symptom_name,
                "object_type": "Symptom",
                "object_canonical_name": symptom_name,
                "evidence": "病蚕常表现为体躯肿胀。",
                "evidence_sha256": marker,
                "source_version_id": marker,
                "chunk_id": marker,
                "publication_id": marker,
                "provenance": {"smoke_marker": marker},
            }
        )
        graph = neo4j.preview(query=marker, limit=10)
        neo4j_ok = len(graph["nodes"]) == 2 and len(graph["edges"]) == 1

        checks = {
            "redis": redis_ok,
            "qdrant": qdrant_ok,
            "opensearch_bm25": opensearch_ok,
            "neo4j": neo4j_ok,
        }
        print(checks)
        if not all(checks.values()):
            raise RuntimeError(f"Knowledge store smoke test failed: {checks}")
    finally:
        if qdrant_client is not None:
            with suppress(Exception):
                qdrant_client.delete_collection(settings.qdrant_collection)
            qdrant_client.close()
        if opensearch_client is not None:
            with suppress(Exception):
                opensearch_client.indices.delete(index=settings.opensearch_index)
            opensearch_client.close()
        with suppress(Exception):
            with neo4j._driver() as driver:
                with driver.session(database=settings.neo4j_database) as session:
                    session.run(
                        "MATCH (n) WHERE n.name IN $names DETACH DELETE n",
                        names=[disease_name, symptom_name],
                    ).consume()


if __name__ == "__main__":
    main()

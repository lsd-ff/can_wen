from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.routes import knowledge as knowledge_route
from app.core.config import Settings
from app.main import app
from app.services.knowledge_graph_service import PublishedKnowledgeGraph


client = TestClient(app)


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def single(self, strict: bool = False):
        if strict and len(self.rows) != 1:
            raise RuntimeError("expected one row")
        return self.rows[0] if self.rows else None


class FakeSession:
    def __init__(self, captured: dict[str, Any]) -> None:
        self.captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def run(self, query: str, **parameters):
        self.captured.setdefault("queries", []).append({"query": query, "parameters": parameters})
        if "RETURN elementId(s) AS source_id" in query:
            return FakeResult(
                [
                    {
                        "source_id": "node-disease",
                        "source_type": "疾病",
                        "source_name": "白僵病",
                        "relation_id": "relation-1",
                        "relation": "表现症状",
                        "target_id": "node-symptom",
                        "target_type": "典型病征",
                        "target_name": "蚕体发白僵硬",
                        "has_evidence": True,
                    }
                ]
            )
        if "RETURN count(r) AS count" in query:
            return FakeResult([{"count": 1}])
        if "UNWIND labels(n) AS label" in query:
            return FakeResult([{"label": "疾病", "count": 1}, {"label": "典型病征", "count": 1}])
        if "RETURN type(r) AS relation, count(*) AS count" in query:
            return FakeResult([{"relation": "表现症状", "count": 1}])
        if "MATCH (n)-[r]-(other)" in query:
            return FakeResult(
                [
                    {
                        "id": "node-disease",
                        "type": "疾病",
                        "name": "白僵病",
                        "description": "由白僵菌感染引起。",
                        "aliases": ["白僵"],
                        "english_label": "White muscardine",
                        "evidence": ["病蚕体表形成白色分生孢子。", "虫体随后逐渐僵硬。"],
                        "source_documents": ["家蚕病理学"],
                        "confidence": 0.95,
                        "review_status": "approved",
                        "degree": 3,
                    }
                ]
            )
        if "WHERE elementId(r) = $element_id" in query:
            return FakeResult(
                [
                    {
                        "id": "relation-1",
                        "relation": "表现症状",
                        "source_id": "node-disease",
                        "source_name": "白僵病",
                        "target_id": "node-symptom",
                        "target_name": "蚕体发白僵硬",
                        "evidence": ["病蚕体表形成白色分生孢子。", "虫体随后逐渐僵硬。"],
                        "source_documents": ["家蚕病理学"],
                        "confidence": 0.95,
                        "review_status": "approved",
                        "publication_id": "publication-current",
                    }
                ]
            )
        raise AssertionError(f"unexpected Cypher: {query}")


class FakeDriver:
    def __init__(self, captured: dict[str, Any]) -> None:
        self.captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def verify_connectivity(self) -> None:
        self.captured["verified"] = True

    def session(self, **kwargs):
        self.captured["session"] = kwargs
        return FakeSession(self.captured)


def _settings() -> Settings:
    return Settings(
        neo4j_uri="neo4j+s://example.databases.neo4j.io",
        neo4j_user="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
    )


def _snapshot() -> dict[str, Any]:
    return {
        "publication_ids": ["publication-current"],
        "neo4j_databases": ["neo4j"],
        "publications": [
            {
                "publication_id": "publication-current",
                "source_title": "家蚕病理学",
                "source_version": "v1",
                "source_url": "https://example.test/source",
                "published_at": "2026-07-23T09:00:00+00:00",
            }
        ],
    }


def test_graph_explore_is_schema_bounded_and_accepts_only_current_or_curated_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import neo4j

    captured: dict[str, Any] = {}
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *args, **kwargs: FakeDriver(captured))

    result = PublishedKnowledgeGraph(_settings()).explore(query="白僵病", limit=6000, snapshot=_snapshot())

    assert captured["verified"] is True
    assert captured["session"] == {"database": "neo4j"}
    assert result["nodes"][0]["type"] == "Disease"
    assert result["edges"][0]["relation_key"] == "HAS_SYMPTOM"
    assert result["edges"][0]["has_evidence"] is True
    assert result["snapshot"]["scope"] == "curated_and_published"
    graph_call = captured["queries"][0]
    assert "coalesce(r.publication_id, '') = ''" in graph_call["query"]
    assert "r.publication_id IN $publication_ids" in graph_call["query"]
    assert graph_call["parameters"]["publication_ids"] == ["publication-current"]
    assert graph_call["parameters"]["limit"] == 5000
    assert result["result"]["limit"] == 5000
    assert set(graph_call["parameters"]["allowed_relations"])
    assert set(graph_call["parameters"]["allowed_labels"])


def test_graph_detail_returns_public_fields_and_traceable_source(monkeypatch: pytest.MonkeyPatch) -> None:
    import neo4j

    captured: dict[str, Any] = {}
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *args, **kwargs: FakeDriver(captured))
    graph = PublishedKnowledgeGraph(_settings())

    node = graph.detail(element_id="node-disease", kind="node", snapshot=_snapshot())
    relationship = graph.detail(element_id="relation-1", kind="relationship", snapshot=_snapshot())

    assert node is not None
    assert node["node"]["aliases"] == ["白僵"]
    assert node["node"]["description"] == "由白僵菌感染引起。"
    assert node["node"]["evidence"] == "病蚕体表形成白色分生孢子。；虫体随后逐渐僵硬。"
    assert relationship is not None
    assert relationship["relationship"]["evidence"] == "病蚕体表形成白色分生孢子。；虫体随后逐渐僵硬。"
    assert relationship["relationship"]["source_record"]["title"] == "家蚕病理学"
    assert all(call["parameters"]["publication_ids"] == ["publication-current"] for call in captured["queries"])


def test_user_graph_routes_require_login() -> None:
    response = client.get("/api/v1/knowledge/graph")

    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}


def test_user_graph_route_exposes_the_sanitized_read_only_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge_route, "get_current_user", lambda *args, **kwargs: object())
    monkeypatch.setattr(knowledge_route, "load_knowledge_snapshot", lambda *args, **kwargs: _snapshot())
    monkeypatch.setattr(
        knowledge_route.PublishedKnowledgeGraph,
        "explore",
        lambda self, **kwargs: {
            "available": True,
            "reason": None,
            "nodes": [
                {
                    "id": "node-disease",
                    "name": "白僵病",
                    "type": "Disease",
                    "type_label": "疾病",
                    "degree": 1,
                }
            ],
            "edges": [],
            "schema": {
                "total_nodes": 1,
                "total_relationships": 0,
                "node_types": [{"key": "Disease", "label": "疾病", "count": 1}],
                "relationship_types": [],
            },
            "result": {
                "node_count": 1,
                "relationship_count": 0,
                "matching_relationships": 0,
                "limit": kwargs["limit"],
                "truncated": False,
                "query": kwargs["query"],
            },
            "snapshot": {
                "scope": "curated_and_published",
                "scope_label": "Neo4j 受控图谱 + 当前已发布知识",
                "source_count": 1,
                "sources": [{"title": "家蚕病理学", "version": "v1"}],
            },
        },
    )

    response = client.get(
        "/api/v1/knowledge/graph?query=白僵病&limit=200",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes"][0]["name"] == "白僵病"
    assert payload["schema"]["node_types"][0]["key"] == "Disease"
    assert payload["snapshot"]["source_count"] == 1
    assert "properties" not in payload["nodes"][0]

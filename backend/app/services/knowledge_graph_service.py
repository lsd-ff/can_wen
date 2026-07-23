from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from app.core.config import Settings


KG_NEO4J_LABELS: dict[str, str] = {
    "Disease": "疾病",
    "DiseaseCategory": "疾病类别",
    "Cause": "病原/致病因素",
    "Symptom": "典型病征",
    "Lesion": "病理变化",
    "Part": "侵染/受害部位",
    "Route": "传播/暴露途径",
    "Condition": "发生条件/诱因",
    "Stage": "发病阶段/时期",
    "Diagnosis": "诊断依据",
    "Measure": "防治措施",
}

KG_NEO4J_RELATION_TYPES: dict[str, str] = {
    "BELONGS_TO": "属于类别",
    "CAUSED_BY": "由……引起",
    "HAS_SYMPTOM": "表现症状",
    "HAS_LESION": "产生病理变化",
    "AFFECTS_PART": "影响部位",
    "HAS_ROUTE": "传播/暴露途径",
    "OCCURS_UNDER": "发生条件",
    "OCCURS_IN": "发病阶段",
    "DIAGNOSED_BY": "诊断依据",
    "CONTROLLED_BY": "防治措施",
}

MAX_GRAPH_RELATIONSHIPS = 5000


class PublishedKnowledgeGraph:
    """Read-only user boundary for the configured Neo4j Aura disease graph.

    The Aura database contains a curated graph created before the current
    publication pipeline as well as versioned relationships created by that
    pipeline. User exploration accepts the curated, schema-bounded records and
    only the publication IDs present in the current immutable snapshot.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _driver(self):
        from neo4j import GraphDatabase

        self.settings.require_neo4j_aura()
        return GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )

    def explore(self, *, query: str, limit: int, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        safe_limit = max(1, min(limit, MAX_GRAPH_RELATIONSHIPS))
        search_text = " ".join(query.split())
        publication_ids = _publication_ids(snapshot)
        parameters = self._query_parameters(snapshot, publication_ids)
        parameters.update({"search_text": search_text, "limit": safe_limit})

        graph_query = f"""
        MATCH (s)-[r]->(o)
        WHERE {_visible_relationship_clause()}
          AND ($search_text = ''
            OR toLower(coalesce(s.name, '')) CONTAINS toLower($search_text)
            OR toLower(coalesce(o.name, '')) CONTAINS toLower($search_text)
            OR any(alias IN coalesce(s.aliases, [])
                   WHERE toLower(toString(alias)) CONTAINS toLower($search_text))
            OR any(alias IN coalesce(o.aliases, [])
                   WHERE toLower(toString(alias)) CONTAINS toLower($search_text)))
        WITH s, r, o
        ORDER BY CASE WHEN s.name = $search_text OR o.name = $search_text THEN 0 ELSE 1 END,
                 coalesce(s.name, ''), type(r), coalesce(o.name, '')
        LIMIT $limit
        RETURN elementId(s) AS source_id, labels(s)[0] AS source_type,
               coalesce(s.name, s.id, elementId(s)) AS source_name,
               elementId(r) AS relation_id, type(r) AS relation,
               elementId(o) AS target_id, labels(o)[0] AS target_type,
               coalesce(o.name, o.id, elementId(o)) AS target_name,
               coalesce(r.latest_evidence, r.evidence, '') <> '' AS has_evidence
        """
        matching_query = f"""
        MATCH (s)-[r]->(o)
        WHERE {_visible_relationship_clause()}
          AND ($search_text = ''
            OR toLower(coalesce(s.name, '')) CONTAINS toLower($search_text)
            OR toLower(coalesce(o.name, '')) CONTAINS toLower($search_text)
            OR any(alias IN coalesce(s.aliases, [])
                   WHERE toLower(toString(alias)) CONTAINS toLower($search_text))
            OR any(alias IN coalesce(o.aliases, [])
                   WHERE toLower(toString(alias)) CONTAINS toLower($search_text)))
        RETURN count(r) AS count
        """
        node_schema_query = f"""
        MATCH (s)-[r]->(o)
        WHERE {_visible_relationship_clause()}
        WITH collect(DISTINCT s) + collect(DISTINCT o) AS connected_nodes
        UNWIND connected_nodes AS n
        WITH DISTINCT n
        UNWIND labels(n) AS label
        RETURN label, count(*) AS count
        ORDER BY count DESC, label
        """
        relationship_schema_query = f"""
        MATCH (s)-[r]->(o)
        WHERE {_visible_relationship_clause()}
        RETURN type(r) AS relation, count(*) AS count
        ORDER BY count DESC, relation
        """

        database = self._database(snapshot)
        with self._driver() as driver:
            driver.verify_connectivity()
            with driver.session(database=database) as session:
                graph_rows = list(session.run(graph_query, **parameters))
                matching_record = session.run(matching_query, **parameters).single(strict=True)
                node_type_rows = list(session.run(node_schema_query, **parameters))
                relationship_type_rows = list(session.run(relationship_schema_query, **parameters))

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        degree: dict[str, int] = {}
        label_keys = {physical: internal for internal, physical in KG_NEO4J_LABELS.items()}
        relationship_keys = {physical: internal for internal, physical in KG_NEO4J_RELATION_TYPES.items()}
        for row in graph_rows:
            source_id = str(row["source_id"])
            target_id = str(row["target_id"])
            source_type = str(row["source_type"])
            target_type = str(row["target_type"])
            relation = str(row["relation"])
            nodes[source_id] = {
                "id": source_id,
                "name": str(row["source_name"]),
                "type": label_keys.get(source_type, source_type),
                "type_label": source_type,
            }
            nodes[target_id] = {
                "id": target_id,
                "name": str(row["target_name"]),
                "type": label_keys.get(target_type, target_type),
                "type_label": target_type,
            }
            degree[source_id] = degree.get(source_id, 0) + 1
            degree[target_id] = degree.get(target_id, 0) + 1
            edges.append(
                {
                    "id": str(row["relation_id"]),
                    "source": source_id,
                    "target": target_id,
                    "relation": relation,
                    "relation_key": relationship_keys.get(relation, relation),
                    "has_evidence": bool(row["has_evidence"]),
                }
            )
        for node_id, node in nodes.items():
            node["degree"] = degree.get(node_id, 0)

        node_types = [
            {
                "key": label_keys.get(str(row["label"]), str(row["label"])),
                "label": str(row["label"]),
                "count": int(row["count"]),
            }
            for row in node_type_rows
        ]
        relationship_types = [
            {
                "key": relationship_keys.get(str(row["relation"]), str(row["relation"])),
                "label": str(row["relation"]),
                "count": int(row["count"]),
            }
            for row in relationship_type_rows
        ]
        matching_relationships = int(matching_record["count"])
        has_publications = bool(publication_ids)
        aura_curated = snapshot.get("kg_mode") == "aura_curated"
        return {
            "available": True,
            "reason": None,
            "nodes": list(nodes.values()),
            "edges": edges,
            "schema": {
                "total_nodes": sum(item["count"] for item in node_types),
                "total_relationships": sum(item["count"] for item in relationship_types),
                "node_types": node_types,
                "relationship_types": relationship_types,
            },
            "result": {
                "node_count": len(nodes),
                "relationship_count": len(edges),
                "matching_relationships": matching_relationships,
                "limit": safe_limit,
                "truncated": matching_relationships > len(edges),
                "query": search_text,
            },
            "snapshot": {
                "scope": "curated_and_published" if has_publications else "curated",
                "scope_label": (
                    "Neo4j Aura 家蚕疾病图谱 + 当前已发布知识"
                    if has_publications
                    else "Neo4j Aura 家蚕疾病图谱（既有数据）"
                    if aura_curated
                    else "Neo4j 受控图谱"
                ),
                "source_count": len(snapshot.get("publications", [])),
                "sources": [_public_source(item) for item in snapshot.get("publications", [])],
            },
        }

    def detail(
        self,
        *,
        element_id: str,
        kind: Literal["node", "relationship"],
        snapshot: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        publication_ids = _publication_ids(snapshot)
        parameters = self._query_parameters(snapshot, publication_ids)
        parameters["element_id"] = element_id
        database = self._database(snapshot)
        label_keys = {physical: internal for internal, physical in KG_NEO4J_LABELS.items()}
        relationship_keys = {physical: internal for internal, physical in KG_NEO4J_RELATION_TYPES.items()}

        with self._driver() as driver:
            driver.verify_connectivity()
            with driver.session(database=database) as session:
                if kind == "node":
                    record = session.run(
                        f"""
                        MATCH (n)-[r]-(other)
                        WHERE elementId(n) = $element_id
                          AND ({_visible_relationship_clause('n', 'r', 'other')})
                        RETURN elementId(n) AS id, labels(n)[0] AS type,
                               coalesce(n.name, n.id, elementId(n)) AS name,
                               coalesce(n.description, '') AS description,
                               coalesce(n.aliases, []) AS aliases,
                               coalesce(n.english_label, '') AS english_label,
                               coalesce(n.evidence, '') AS evidence,
                               coalesce(n.source_docs, []) AS source_documents,
                               n.confidence AS confidence,
                               coalesce(n.review_status, '') AS review_status,
                               count(DISTINCT r) AS degree
                        """,
                        **parameters,
                    ).single()
                    if record is None:
                        return None
                    physical_type = str(record["type"])
                    return {
                        "kind": "node",
                        "node": {
                            "id": str(record["id"]),
                            "name": str(record["name"]),
                            "type": label_keys.get(physical_type, physical_type),
                            "type_label": physical_type,
                            "degree": int(record["degree"]),
                            "description": _optional_text(record["description"]),
                            "aliases": _string_list(record["aliases"]),
                            "english_label": _optional_text(record["english_label"]),
                            "evidence": _evidence_text(record["evidence"]),
                            "source_documents": _string_list(record["source_documents"]),
                            "confidence": _scalar(record["confidence"]),
                            "review_status": _optional_text(record["review_status"]),
                        },
                        "relationship": None,
                    }

                record = session.run(
                    f"""
                    MATCH (s)-[r]->(o)
                    WHERE elementId(r) = $element_id
                      AND ({_visible_relationship_clause()})
                    RETURN elementId(r) AS id, type(r) AS relation,
                           elementId(s) AS source_id,
                           coalesce(s.name, s.id, elementId(s)) AS source_name,
                           elementId(o) AS target_id,
                           coalesce(o.name, o.id, elementId(o)) AS target_name,
                           coalesce(r.latest_evidence, r.evidence, '') AS evidence,
                           coalesce(r.source_docs, []) AS source_documents,
                           r.confidence AS confidence,
                           coalesce(r.review_status, '') AS review_status,
                           coalesce(r.publication_id, '') AS publication_id
                    """,
                    **parameters,
                ).single()
                if record is None:
                    return None
                relation = str(record["relation"])
                publication_id = str(record["publication_id"])
                source_record = _publication_source_map(snapshot).get(publication_id)
                return {
                    "kind": "relationship",
                    "node": None,
                    "relationship": {
                        "id": str(record["id"]),
                        "source": str(record["source_id"]),
                        "source_name": str(record["source_name"]),
                        "target": str(record["target_id"]),
                        "target_name": str(record["target_name"]),
                        "relation": relation,
                        "relation_key": relationship_keys.get(relation, relation),
                        "evidence": _evidence_text(record["evidence"]),
                        "source_documents": _string_list(record["source_documents"]),
                        "confidence": _scalar(record["confidence"]),
                        "review_status": _optional_text(record["review_status"]),
                        "source_record": _public_source(source_record) if source_record else None,
                    },
                }

    def _database(self, snapshot: Mapping[str, Any]) -> str:
        # The user-selected Aura instance is the only permitted user-side KG
        # target. Build metadata must never redirect a graph request elsewhere.
        return self.settings.neo4j_database

    @staticmethod
    def _query_parameters(snapshot: Mapping[str, Any], publication_ids: list[str]) -> dict[str, Any]:
        return {
            "publication_ids": publication_ids,
            "allowed_labels": list(KG_NEO4J_LABELS.values()),
            "allowed_relations": list(KG_NEO4J_RELATION_TYPES.values()),
        }


def empty_graph_response(reason: str, *, limit: int, query: str = "") -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "nodes": [],
        "edges": [],
        "schema": {"total_nodes": 0, "total_relationships": 0, "node_types": [], "relationship_types": []},
        "result": {
            "node_count": 0,
            "relationship_count": 0,
            "matching_relationships": 0,
            "limit": limit,
            "truncated": False,
            "query": " ".join(query.split()),
        },
        "snapshot": {"scope": "curated", "scope_label": "Neo4j 受控图谱", "source_count": 0, "sources": []},
    }


def _visible_relationship_clause(subject: str = "s", relation: str = "r", object_: str = "o") -> str:
    return (
        f"type({relation}) IN $allowed_relations "
        f"AND any(label IN labels({subject}) WHERE label IN $allowed_labels) "
        f"AND any(label IN labels({object_}) WHERE label IN $allowed_labels) "
        f"AND (coalesce({relation}.publication_id, '') = '' "
        f"OR {relation}.publication_id IN $publication_ids)"
    )


def _publication_ids(snapshot: Mapping[str, Any]) -> list[str]:
    return [str(value) for value in snapshot.get("publication_ids", []) if str(value).strip()]


def _publication_source_map(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("publication_id")): item
        for item in snapshot.get("publications", [])
        if isinstance(item, Mapping) and item.get("publication_id")
    }


def _public_source(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": str(item.get("source_title") or "已发布知识文档"),
        "version": _optional_text(item.get("source_version")),
        "url": _optional_text(item.get("source_url")),
        "published_at": _optional_text(item.get("published_at")),
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in values:
        cleaned = " ".join(str(item).split())
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result[:40]


def _evidence_text(value: Any) -> str | None:
    if isinstance(value, (list, tuple, set)):
        parts = [_optional_text(item) for item in value]
        return "；".join(part for part in parts if part) or None
    return _optional_text(value)


def _scalar(value: Any) -> str | float | int | None:
    if value is None or isinstance(value, (str, float, int)):
        return value
    return str(value)

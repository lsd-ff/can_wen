from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


KG_SCHEMA_LABELS: tuple[str, ...] = (
    "Disease",
    "DiseaseCategory",
    "Cause",
    "Symptom",
    "Lesion",
    "Part",
    "Route",
    "Condition",
    "Stage",
    "Diagnosis",
    "Measure",
)

KG_RELATIONS: dict[str, tuple[str, str]] = {
    "BELONGS_TO": ("Disease", "DiseaseCategory"),
    "CAUSED_BY": ("Disease", "Cause"),
    "HAS_SYMPTOM": ("Disease", "Symptom"),
    "HAS_LESION": ("Disease", "Lesion"),
    "AFFECTS_PART": ("Disease", "Part"),
    "HAS_ROUTE": ("Disease", "Route"),
    "OCCURS_UNDER": ("Disease", "Condition"),
    "OCCURS_IN": ("Disease", "Stage"),
    "DIAGNOSED_BY": ("Disease", "Diagnosis"),
    "CONTROLLED_BY": ("Disease", "Measure"),
}

# The agents use stable English keys, while the existing Aura graph keeps the
# user-facing Chinese labels and relationship types from the approved schema.
# This boundary mapping prevents a second, parallel set of English-labelled
# nodes from being created when a build is published.
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


@dataclass(frozen=True)
class NormalizationResult:
    surface: str
    canonical: str
    status: str
    relation: str | None = None
    note: str = ""

    @property
    def requires_review(self) -> bool:
        return self.status not in {"confirmed", "unchanged"}


class SilkwormGlossary:
    """Traceable glossary and explicit entity-normalization rules.

    Only rules marked ``confirmed`` are applied automatically. Ambiguous and
    context-dependent names remain unchanged and are sent to review.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        terms = tuple(payload.get("terms", []))
        self._terms_by_name = {str(item["name"]): item for item in terms}
        self._rules = {str(rule["surface"]): rule for rule in payload.get("normalization_rules", [])}

    @classmethod
    def from_path(cls, path: Path) -> "SilkwormGlossary":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    @lru_cache(maxsize=1)
    def default(cls) -> "SilkwormGlossary":
        repository_root = Path(__file__).resolve().parents[3]
        path = repository_root / "backend" / "docs" / "knowledge" / "silkworm_domain_glossary.json"
        return cls.from_path(path)

    def normalize(self, surface: str) -> NormalizationResult:
        cleaned = " ".join(surface.strip().split())
        rule = self._rules.get(cleaned)
        if rule is None:
            return NormalizationResult(cleaned, cleaned, "unchanged")
        status = str(rule.get("review_status", "context_required"))
        canonical = str(rule.get("canonical", cleaned))
        if status != "confirmed":
            canonical = cleaned
        return NormalizationResult(
            surface=cleaned,
            canonical=canonical,
            status=status,
            relation=str(rule.get("relation", "")) or None,
            note=str(rule.get("note", "")),
        )

    def known_term(self, name: str, label: str | None = None) -> bool:
        item = self._terms_by_name.get(name.strip())
        return bool(item and (label is None or item.get("label") == label))

def validate_triple_types(subject_type: str, relation: str, object_type: str) -> list[str]:
    flags: list[str] = []
    if subject_type not in KG_SCHEMA_LABELS:
        flags.append("unknown_subject_type")
    if object_type not in KG_SCHEMA_LABELS:
        flags.append("unknown_object_type")
    expected = KG_RELATIONS.get(relation)
    if expected is None:
        flags.append("unknown_relation")
    elif expected != (subject_type, object_type):
        flags.append("relation_type_mismatch")
    return flags

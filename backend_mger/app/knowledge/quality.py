from __future__ import annotations

import re
from dataclasses import dataclass

from app.knowledge.schema import SilkwormGlossary, validate_triple_types
from app.knowledge.types import DocumentChunk, QAExtraction, TripleExtraction


NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:\s*(?:%|℃|°C|mg/kg|mg/L|g/m³|mL/m²|小时|分钟|天))?")
VAGUE_QUESTION_RE = re.compile(
    r"^(?:它|这|这个|该内容|上述内容|文中)(?:应该|应当|需要|要)?(?:是|有|为什么|如何|怎么)"
)


@dataclass(frozen=True)
class QualityResult:
    score: float
    flags: tuple[str, ...]

    @property
    def requires_review(self) -> bool:
        return bool(self.flags) or self.score < 0.9


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def evidence_is_supported(evidence: str, content: str) -> bool:
    compact_evidence = _compact(evidence)
    return bool(compact_evidence) and compact_evidence in _compact(content)


def validate_qa(item: QAExtraction, chunk: DocumentChunk) -> QualityResult:
    flags: list[str] = []
    question = item.question.strip()
    answer = item.answer.strip()
    if len(question) < 7:
        flags.append("question_too_generic")
    if VAGUE_QUESTION_RE.search(question):
        flags.append("question_context_dependent")
    if len(answer) < 10:
        flags.append("answer_too_short")
    if not evidence_is_supported(item.evidence, chunk.content):
        flags.append("evidence_missing")
    answer_numbers = set(NUMBER_RE.findall(answer))
    content_numbers = set(NUMBER_RE.findall(chunk.content))
    if answer_numbers - content_numbers:
        flags.append("unsupported_parameter")
    if chunk.quality_score < 0.6:
        flags.append("low_quality_chunk")
    if not item.keywords:
        flags.append("keywords_missing")
    deductions = {
        "question_too_generic": 0.15,
        "question_context_dependent": 0.18,
        "answer_too_short": 0.2,
        "evidence_missing": 0.5,
        "unsupported_parameter": 0.35,
        "low_quality_chunk": 0.25,
        "keywords_missing": 0.05,
    }
    score = min(item.confidence, 1.0) - sum(deductions[flag] for flag in flags)
    return QualityResult(max(0.0, round(score, 3)), tuple(dict.fromkeys(flags)))


def validate_triple(
    item: TripleExtraction,
    chunk: DocumentChunk,
    glossary: SilkwormGlossary,
) -> tuple[QualityResult, str, str, dict[str, str]]:
    flags = validate_triple_types(item.subject_type, item.relation, item.object_type)
    if not evidence_is_supported(item.evidence, chunk.content):
        flags.append("evidence_missing")

    subject = glossary.normalize(item.subject_name)
    object_ = glossary.normalize(item.object_name)
    if subject.requires_review:
        flags.append("ambiguous_subject")
    if object_.requires_review:
        flags.append("ambiguous_object")
    if item.subject_type == "Disease" and not glossary.known_term(subject.canonical, "Disease"):
        flags.append("unknown_disease")
    if chunk.quality_score < 0.6:
        flags.append("low_quality_chunk")

    deductions = {
        "unknown_subject_type": 0.5,
        "unknown_object_type": 0.5,
        "unknown_relation": 0.5,
        "relation_type_mismatch": 0.5,
        "evidence_missing": 0.5,
        "ambiguous_subject": 0.35,
        "ambiguous_object": 0.25,
        "unknown_disease": 0.3,
        "low_quality_chunk": 0.2,
    }
    score = min(item.confidence, 1.0) - sum(deductions.get(flag, 0.1) for flag in flags)
    resolution = {
        "subject_surface": subject.surface,
        "subject_status": subject.status,
        "subject_note": subject.note,
        "object_surface": object_.surface,
        "object_status": object_.status,
        "object_note": object_.note,
    }
    return (
        QualityResult(max(0.0, round(score, 3)), tuple(dict.fromkeys(flags))),
        subject.canonical,
        object_.canonical,
        resolution,
    )

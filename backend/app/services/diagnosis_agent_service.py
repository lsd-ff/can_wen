from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.agents.diagnosis import AgentPublicEvent, DiagnosisAgentResult, DiagnosisAgentWorkflow
from app.agents.diagnosis.knowledge import load_knowledge_snapshot
from app.agents.diagnosis.types import Citation, EvidenceItem
from app.core.config import Settings
from app.core.security import now_utc
from app.db.session import SessionLocal
from app.models import AgentEvidence, AgentRun, AgentRunEvent, Conversation, Message, User
from app.schemas.diagnosis import (
    DiagnosisAgentEventResponse,
    DiagnosisAgentRunResponse,
    DiagnosisCitationResponse,
)
from app.services.llm_client import OpenAICompatibleModelConfig


@dataclass(frozen=True)
class DiagnosisAgentExecution:
    run_id: UUID
    result: DiagnosisAgentResult
    events: list[DiagnosisAgentEventResponse]

    def response(self) -> DiagnosisAgentRunResponse:
        return DiagnosisAgentRunResponse(
            id=str(self.run_id),
            status=self.result.status,
            route=self.result.route,
            risk_level=self.result.risk_level,
            original_question=self.result.original_question,
            rewritten_question=self.result.rewritten_question,
            evidence_status=self.result.evidence_status,
            missing_slots=self.result.missing_slots,
            metrics=self.result.metrics,
            citations=[_citation_response(item) for item in self.result.citations],
            events=self.events,
            started_at=self.events[0].created_at if self.events else None,
            completed_at=self.events[-1].created_at if self.events else None,
            created_at=self.events[0].created_at if self.events else now_utc(),
        )


class AgentEventRecorder:
    """Persist public events before forwarding them to an SSE listener."""

    def __init__(self, run_id: UUID, callback=None) -> None:
        self.run_id = run_id
        self.callback = callback
        self._lock = threading.Lock()
        with SessionLocal() as db:
            self._sequence = int(
                db.scalar(
                    select(func.coalesce(func.max(AgentRunEvent.sequence), 0)).where(
                        AgentRunEvent.agent_run_id == run_id
                    )
                )
                or 0
            )

    def __call__(
        self,
        *,
        agent: str,
        stage: str,
        status: str,
        title: str,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
        internal_payload: dict[str, Any] | None = None,
    ) -> AgentPublicEvent:
        with self._lock:
            self._sequence += 1
            created_at = now_utc()
            public_payload = _public_payload(payload or {})
            event = AgentRunEvent(
                agent_run_id=self.run_id,
                sequence=self._sequence,
                agent_key=agent,
                stage=stage,
                status=status,
                public_title=title[:240],
                public_summary=(summary or "")[:1000] or None,
                public_payload=public_payload,
                internal_payload=_internal_payload(internal_payload or {}),
                created_at=created_at,
            )
            with SessionLocal() as db:
                db.add(event)
                db.commit()
            public_event = AgentPublicEvent(
                run_id=str(self.run_id),
                sequence=self._sequence,
                agent=agent,
                stage=stage,
                status=status,
                title=title[:240],
                summary=(summary or "")[:1000] or None,
                payload=public_payload,
                created_at=created_at,
            )
            if self.callback is not None:
                self.callback(public_event)
            return public_event


def execute_diagnosis_agent(
    db: Session,
    *,
    user: User,
    conversation: Conversation,
    user_message: Message,
    settings: Settings,
    model_config: OpenAICompatibleModelConfig,
    original_question: str,
    history: list[Any],
    structured_data: dict[str, Any] | None = None,
    multimodal_observations: dict[str, Any] | None = None,
    user_preferences: dict[str, Any] | None = None,
    event_callback=None,
    workflow_factory=DiagnosisAgentWorkflow,
) -> DiagnosisAgentExecution:
    snapshot = load_knowledge_snapshot(db)
    pending_slots = _pending_clarification_slots(db, conversation_id=conversation.id)
    run = AgentRun(
        user_id=user.id,
        conversation_id=conversation.id,
        trigger_message_id=user_message.id,
        status="running",
        original_question=original_question.strip() or "请分析本轮上传的家蚕问诊材料",
        knowledge_snapshot=snapshot,
        started_at=now_utc(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    recorder = AgentEventRecorder(run.id, callback=event_callback)
    recorder(
        agent="orchestrator",
        stage="start",
        status="started",
        title="四智能体流程已启动",
        summary="将依次完成问题理解、按路由检索、证据治理和引用回答。",
        payload={
            "knowledge_source_count": int(snapshot.get("source_count", 0)),
            "long_term_memory_enabled": False,
        },
    )
    normalized_history = [
        {
            "role": str(getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else "user")),
            "content": str(getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "")),
        }
        for item in history
    ]
    try:
        workflow = workflow_factory(settings=settings, model_config=model_config)
        result = workflow.invoke(
            run_id=str(run.id),
            original_question=run.original_question,
            conversation_summary=(conversation.summary or "").strip(),
            history=normalized_history,
            structured_data=structured_data or {},
            multimodal_observations=multimodal_observations or {},
            pending_slots=pending_slots,
            user_preferences=user_preferences or {},
            model_config=model_config,
            knowledge_snapshot=snapshot,
            emit=recorder,
        )
    except Exception as error:
        recorder(
            agent="orchestrator",
            stage="failed",
            status="failed",
            title="智能体流程未完成",
            summary="系统没有返回无证据的大模型答案，请稍后重试。",
            payload={"retryable": True},
            internal_payload={"error_type": error.__class__.__name__},
        )
        result = DiagnosisAgentResult(
            answer="智能体流程本轮未完成，我没有改用纯大模型答案。请稍后重试；若现场正在大量死亡或快速扩散，请先隔离异常蚕并联系当地蚕桑技术人员。",
            status="failed",
            route="clarify",
            risk_level="low",
            original_question=run.original_question,
            rewritten_question=run.original_question,
            evidence_status="insufficient",
            missing_slots=[],
            metrics={"fatal_error": error.__class__.__name__},
        )

    run.status = result.status
    run.route = result.route
    run.risk_level = result.risk_level
    run.rewritten_question = result.rewritten_question
    run.context_pack = result.context_pack
    run.metrics = {
        **result.metrics,
        "evidence_status": result.evidence_status,
        "missing_slots": result.missing_slots,
        "citations": [item.model_dump(mode="json") for item in result.citations],
    }
    run.error_message = result.metrics.get("fatal_error") if result.status == "failed" else None
    run.completed_at = now_utc()
    db.add(run)
    _persist_evidence(db, run_id=run.id, evidence=result.evidence)
    db.commit()
    events = list_agent_run_events(db, user=user, run_id=run.id)
    return DiagnosisAgentExecution(run_id=run.id, result=result, events=events)


def link_agent_run_to_assistant_message(
    db: Session,
    *,
    execution: DiagnosisAgentExecution,
    assistant_message: Message,
) -> None:
    run = db.get(AgentRun, execution.run_id)
    if run is not None:
        run.assistant_message_id = assistant_message.id
        db.add(run)


def get_agent_run_response(db: Session, *, user: User, run_id: UUID) -> DiagnosisAgentRunResponse:
    run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体运行记录不存在")
    metrics = run.metrics or {}
    citations = [
        DiagnosisCitationResponse.model_validate(item)
        for item in metrics.get("citations", [])
        if isinstance(item, dict)
    ]
    return DiagnosisAgentRunResponse(
        id=str(run.id),
        status=run.status,
        route=run.route,
        risk_level=run.risk_level,
        original_question=run.original_question,
        rewritten_question=run.rewritten_question,
        evidence_status=metrics.get("evidence_status"),
        missing_slots=metrics.get("missing_slots", []),
        metrics={key: value for key, value in metrics.items() if key not in {"citations", "missing_slots"}},
        citations=citations,
        events=list_agent_run_events(db, user=user, run_id=run.id),
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def list_agent_run_events(
    db: Session,
    *,
    user: User,
    run_id: UUID,
    after_sequence: int = 0,
) -> list[DiagnosisAgentEventResponse]:
    owned = db.scalar(select(AgentRun.id).where(AgentRun.id == run_id, AgentRun.user_id == user.id))
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体运行记录不存在")
    rows = db.scalars(
        select(AgentRunEvent)
        .where(AgentRunEvent.agent_run_id == run_id, AgentRunEvent.sequence > max(0, after_sequence))
        .order_by(AgentRunEvent.sequence.asc())
    ).all()
    return [_event_response(row) for row in rows]


def agent_run_from_message_metadata(metadata: dict[str, Any]) -> DiagnosisAgentRunResponse | None:
    payload = metadata.get("agent_run")
    if not isinstance(payload, dict):
        return None
    try:
        return DiagnosisAgentRunResponse.model_validate(payload)
    except (TypeError, ValueError):
        return None


def _pending_clarification_slots(db: Session, *, conversation_id: UUID) -> list[str]:
    previous = db.scalar(
        select(AgentRun)
        .where(
            AgentRun.conversation_id == conversation_id,
            AgentRun.status == "waiting_for_user",
        )
        .order_by(desc(AgentRun.created_at))
    )
    if previous is None:
        return []
    values = (previous.metrics or {}).get("missing_slots", [])
    return [str(value) for value in values if str(value).strip()][:8] if isinstance(values, list) else []


def _persist_evidence(db: Session, *, run_id: UUID, evidence: list[EvidenceItem]) -> None:
    for item in evidence:
        score = Decimal(str(item.score)).quantize(Decimal("0.000001")) if item.score is not None else None
        db.add(
            AgentEvidence(
                agent_run_id=run_id,
                evidence_key=item.evidence_key,
                evidence_type=item.evidence_type,
                retriever=item.retriever,
                title=item.title,
                content=item.content,
                source_name=item.source_name,
                source_uri=item.source_uri,
                source_version=item.source_version,
                source_page=item.source_page,
                score=score,
                rank_order=item.rank_order,
                metadata_=item.metadata,
            )
        )


def _event_response(row: AgentRunEvent) -> DiagnosisAgentEventResponse:
    return DiagnosisAgentEventResponse(
        run_id=str(row.agent_run_id),
        sequence=int(row.sequence),
        agent=row.agent_key,
        stage=row.stage,
        status=row.status,
        title=row.public_title,
        summary=row.public_summary,
        payload=row.public_payload or {},
        created_at=row.created_at,
    )


def _citation_response(item: Citation) -> DiagnosisCitationResponse:
    return DiagnosisCitationResponse.model_validate(item.model_dump())


def _public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key)[:80]: _public_payload(item)
            for key, item in value.items()
            if not _is_sensitive_payload_key(str(key))
        }
    if isinstance(value, list):
        return [_public_payload(item) for item in value[:30]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:500] if isinstance(value, str) else value
    return str(value)[:500]


def _is_sensitive_payload_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in {
        "prompt",
        "system_prompt",
        "user_prompt",
        "api_key",
        "authorization",
        "password",
        "secret",
        "access_token",
        "refresh_token",
        "vector",
        "embedding",
        "cypher",
    }:
        return True
    return (
        normalized.endswith(("_api_key", "_password", "_secret", "_token"))
        or "embedding" in normalized
        or "vector" in normalized
        or "cypher" in normalized
    )


def _internal_payload(value: dict[str, Any]) -> dict[str, Any]:
    # Internal audit fields are deliberately constrained too; secrets, prompts,
    # vectors and raw model reasoning are never persisted here.
    return _public_payload(value)

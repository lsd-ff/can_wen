from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.diagnosis.answer import EvidenceAnswerAgent
from app.agents.diagnosis.context import ContextRoutingAgent
from app.agents.diagnosis.gateway import DiagnosisAgentGateway
from app.agents.diagnosis.retrieval import KGRetrievalAgent, RAGRetrievalAgent
from app.agents.diagnosis.types import AgentState, DiagnosisAgentResult, EventEmitter
from app.core.config import Settings
from app.services.llm_client import OpenAICompatibleModelConfig


class DiagnosisAgentWorkflow:
    """LangGraph orchestration for the four public diagnosis agents."""

    def __init__(
        self,
        *,
        settings: Settings,
        model_config: OpenAICompatibleModelConfig,
        gateway: DiagnosisAgentGateway | None = None,
        context_agent: ContextRoutingAgent | None = None,
        kg_agent: KGRetrievalAgent | None = None,
        rag_agent: RAGRetrievalAgent | None = None,
        answer_agent: EvidenceAnswerAgent | None = None,
    ) -> None:
        self.settings = settings
        self.gateway = gateway or DiagnosisAgentGateway(settings, model_config)
        self.context_agent = context_agent or ContextRoutingAgent(self.gateway)
        self.kg_agent = kg_agent or KGRetrievalAgent(settings, self.gateway)
        self.rag_agent = rag_agent or RAGRetrievalAgent(settings, self.gateway)
        self.answer_agent = answer_agent or EvidenceAnswerAgent(
            self.gateway,
            final_evidence_limit=settings.diagnosis_agent_final_evidence_limit,
        )
        self.graph = self._build_graph()

    def invoke(
        self,
        *,
        run_id: str,
        original_question: str,
        conversation_summary: str,
        history: list[dict[str, str]],
        structured_data: dict[str, Any],
        multimodal_observations: dict[str, Any],
        pending_slots: list[str],
        user_preferences: dict[str, Any],
        model_config: OpenAICompatibleModelConfig,
        knowledge_snapshot: dict[str, Any],
        emit: EventEmitter,
    ) -> DiagnosisAgentResult:
        initial: AgentState = {
            "run_id": run_id,
            "original_question": original_question,
            "conversation_summary": conversation_summary,
            "history": history,
            "structured_data": structured_data,
            "multimodal_observations": multimodal_observations,
            "pending_slots": pending_slots,
            "user_preferences": user_preferences,
            "settings": self.settings,
            "model_config": model_config,
            "knowledge_snapshot": knowledge_snapshot,
            "emit": emit,
            "rag_evidence": [],
            "kg_evidence": [],
            "branch_metrics": [],
            "branch_errors": [],
        }
        final_state = self.graph.invoke(initial, config={"configurable": {"thread_id": run_id}})
        return final_state["result"]

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("agent1_context_router", self.context_agent)
        builder.add_node("agent2_kg", self.kg_agent)
        builder.add_node("agent3_rag", self.rag_agent)
        builder.add_node("hybrid_dispatch", self._hybrid_retrieval)
        builder.add_node("agent4_evidence_answer", self.answer_agent)
        builder.add_edge(START, "agent1_context_router")
        builder.add_conditional_edges(
            "agent1_context_router",
            self._route_after_understanding,
            {
                "kg": "agent2_kg",
                "rag": "agent3_rag",
                "hybrid": "hybrid_dispatch",
                "answer": "agent4_evidence_answer",
            },
        )
        builder.add_edge("agent2_kg", "agent4_evidence_answer")
        builder.add_edge("agent3_rag", "agent4_evidence_answer")
        builder.add_edge("hybrid_dispatch", "agent4_evidence_answer")
        builder.add_edge("agent4_evidence_answer", END)
        return builder.compile()

    @staticmethod
    def _route_after_understanding(state: AgentState) -> str:
        route = state["query_plan"].route
        return route if route in {"rag", "kg", "hybrid"} else "answer"

    def _hybrid_retrieval(self, state: AgentState) -> dict[str, Any]:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="hybrid-agent") as executor:
            kg_future = executor.submit(self.kg_agent, state)
            rag_future = executor.submit(self.rag_agent, state)
            kg_result = kg_future.result()
            rag_result = rag_future.result()
        return {
            "kg_evidence": kg_result.get("kg_evidence", []),
            "rag_evidence": rag_result.get("rag_evidence", []),
            "branch_metrics": [
                *kg_result.get("branch_metrics", []),
                *rag_result.get("branch_metrics", []),
            ],
            "branch_errors": [
                *kg_result.get("branch_errors", []),
                *rag_result.get("branch_errors", []),
            ],
        }

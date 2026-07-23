import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.agents.diagnosis.knowledge import load_knowledge_snapshot
from app.api.routes.auth import _bearer_token
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.knowledge import KnowledgeGraphDetailResponse, KnowledgeGraphResponse
from app.services.auth_service import get_current_user
from app.services.knowledge_graph_service import (
    MAX_GRAPH_RELATIONSHIPS,
    PublishedKnowledgeGraph,
    empty_graph_response,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/graph", response_model=KnowledgeGraphResponse)
def explore_knowledge_graph(
    request: Request,
    query: str = Query(default="", max_length=80),
    limit: int = Query(default=700, ge=1, le=MAX_GRAPH_RELATIONSHIPS),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeGraphResponse:
    get_current_user(db, access_token=_bearer_token(request))
    snapshot = load_knowledge_snapshot(db)
    try:
        payload = PublishedKnowledgeGraph(settings).explore(query=query, limit=limit, snapshot=snapshot)
    except RuntimeError as error:
        logger.warning("User knowledge graph configuration unavailable: %s", error)
        payload = empty_graph_response(str(error), limit=limit, query=query)
    except Exception as error:
        logger.exception("User knowledge graph exploration failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j Aura 图谱暂不可用：{error.__class__.__name__}",
        ) from error
    return KnowledgeGraphResponse.model_validate(payload)


@router.get("/graph/detail", response_model=KnowledgeGraphDetailResponse)
def get_knowledge_graph_detail(
    request: Request,
    element_id: str = Query(min_length=1, max_length=200),
    kind: Literal["node", "relationship"] = Query(),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeGraphDetailResponse:
    get_current_user(db, access_token=_bearer_token(request))
    snapshot = load_knowledge_snapshot(db)
    try:
        payload = PublishedKnowledgeGraph(settings).detail(
            element_id=element_id,
            kind=kind,
            snapshot=snapshot,
        )
    except Exception as error:
        logger.exception("User knowledge graph detail failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j Aura 图谱暂不可用：{error.__class__.__name__}",
        ) from error
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图谱元素不存在或不在当前可见范围内")
    return KnowledgeGraphDetailResponse.model_validate(payload)

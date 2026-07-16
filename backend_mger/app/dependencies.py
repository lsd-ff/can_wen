from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import AdminActor, current_actor, require


def get_actor(request: Request, db: Session = Depends(get_db)) -> AdminActor:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录管理后台")
    return current_actor(db, token=token.strip())


def require_permission(permission: str) -> Callable[[AdminActor], AdminActor]:
    def dependency(actor: AdminActor = Depends(get_actor)) -> AdminActor:
        require(actor, permission)
        return actor

    return dependency

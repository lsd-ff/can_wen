from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal, close_database
from app.models import Base
from app.knowledge.model_registry import seed_knowledge_model_configs
from app.routes.auth import router as auth_router
from app.routes.community import router as community_router
from app.routes.knowledge import router as knowledge_router
from app.routes.reviews import router as reviews_router
from app.routes.system import router as system_router
from app.routes.users import router as users_router
from app.routes.workbench import router as workbench_router
from app.services import bootstrap_super_admin, ensure_admin_schema, seed_rbac


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    with SessionLocal() as session:
        ensure_admin_schema(session)
        if settings.auto_create_schema:
            Base.metadata.create_all(bind=session.get_bind())
        seed_rbac(session)
        seed_knowledge_model_configs(session, settings)
        bootstrap_super_admin(session)
    yield
    close_database()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(workbench_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(community_router, prefix=settings.api_prefix)
app.include_router(reviews_router, prefix=settings.api_prefix)
app.include_router(knowledge_router, prefix=settings.api_prefix)
app.include_router(system_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} is running"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

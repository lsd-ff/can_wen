from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.diagnosis import router as diagnosis_router
from app.api.routes.model_configs import router as model_configs_router
from app.api.routes.projects import router as projects_router
from app.api.routes.community import router as community_router
from app.api.routes.husbandry import router as husbandry_router
from app.api.routes.user_settings import router as user_settings_router
from app.api.routes.admin import router as admin_router
from app.core.config import get_settings
from app.core.middleware import InMemoryRateLimitMiddleware, SecurityHeadersMiddleware
from app.db.session import close_database_engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    yield
    close_database_engine()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    InMemoryRateLimitMiddleware,
    requests_per_minute=settings.api_rate_limit_requests_per_minute,
    auth_requests_per_minute=settings.auth_rate_limit_requests_per_minute,
)
if settings.security_headers_enabled:
    app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(diagnosis_router, prefix=settings.api_v1_prefix)
app.include_router(model_configs_router, prefix=settings.api_v1_prefix)
app.include_router(projects_router, prefix=settings.api_v1_prefix)
app.include_router(community_router, prefix=settings.api_v1_prefix)
app.include_router(husbandry_router, prefix=settings.api_v1_prefix)
app.include_router(user_settings_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": f"{settings.app_name} is running"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Lightweight liveness probe used by the management console."""
    return {"status": "ok"}

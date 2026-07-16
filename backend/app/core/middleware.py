from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline browser hardening headers to every API response."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return response


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Small per-process guard for public endpoints; production can replace it with Redis."""

    _AUTH_PATHS = {
        "/api/v1/auth/email/verification-codes",
        "/api/v1/auth/email/login",
        "/api/v1/auth/phone/verification-codes",
        "/api/v1/auth/phone/login",
        "/api/v1/auth/refresh",
    }

    def __init__(self, app, *, requests_per_minute: int, auth_requests_per_minute: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.requests_per_minute = max(1, requests_per_minute)
        self.auth_requests_per_minute = max(1, auth_requests_per_minute)
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        is_auth = request.url.path in self._AUTH_PATHS
        limit = self.auth_requests_per_minute if is_auth else self.requests_per_minute
        forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        client = forwarded_for or (request.client.host if request.client else "unknown")
        key = f"{'auth' if is_auth else 'api'}:{client}"
        now = monotonic()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(max(1, int(60 - (now - bucket[0]))))},
            )
        bucket.append(now)
        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(limit))
        return response

"""HTTP 安全標頭與記憶體速率限制中介層。"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """單一程序的固定時間窗限制；多實例部署時應改用 Redis。"""

    def __init__(self, app, *, general_limit: int = 120, login_limit: int = 5, window_seconds: int = 60):
        super().__init__(app)
        self.general_limit = general_limit
        self.login_limit = login_limit
        self.window_seconds = window_seconds
        self.requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in {"/health", "/docs", "/redoc", "/openapi.json"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        is_login = request.url.path.endswith("/auth/login") or request.url.path.endswith("/auth/login/form")
        scope = "login" if is_login else "general"
        limit = self.login_limit if is_login else self.general_limit
        now = time.monotonic()
        bucket = self.requests[(client_ip, scope)]
        while bucket and bucket[0] <= now - self.window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limit_exceeded", "message": "請求過於頻繁，請稍後再試"}},
                headers={"Retry-After": str(self.window_seconds)},
            )
        if is_login:
            response = await call_next(request)
            if response.status_code >= 400:
                bucket.append(now)
            return response
        bucket.append(now)
        return await call_next(request)

    def clear(self) -> None:
        self.requests.clear()

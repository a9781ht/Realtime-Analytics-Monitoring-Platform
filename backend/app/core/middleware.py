"""HTTP 中介層：請求 ID、耗時統計、系統日誌寫入。"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import get_logger
from app.services import log_service

logger = get_logger("app.request")

# 為避免日誌量過大，僅寫入資料庫的條件：非 GET 請求或發生錯誤
_SKIP_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "request failed",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": duration_ms,
                },
            )
            await log_service.write_log(
                level="ERROR",
                action="http.request",
                message="未處理的例外",
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else None,
            )
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)

        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )

        path = request.url.path
        if path not in _SKIP_PATHS and (request.method != "GET" or status_code >= 400):
            await log_service.write_log(
                level="WARNING" if status_code >= 400 else "INFO",
                action="http.request",
                message=f"{request.method} {path} -> {status_code}",
                method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else None,
            )

        return response

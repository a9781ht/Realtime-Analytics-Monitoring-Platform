"""FastAPI 應用程式進入點。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import get_logger, setup_logging
from app.core.middleware import RequestLogMiddleware
from app.core.security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.db.init_db import seed_demo_data
from app.db.session import engine
from app.services.generator import generator

setup_logging()
logger = get_logger(__name__)

DESCRIPTION = """
### 即時資料分析與監控系統 API

| 模組 | 說明 |
| --- | --- |
| **Auth** | 註冊、登入、JWT Token 換發 |
| **Users** | 個人資料維護、使用者管理（Admin） |
| **Records** | 資料 CRUD、分頁 / 篩選 / 排序、CSV / JSON 批量匯入 |
| **Analytics** | 統計摘要、分類聚合、趨勢分析、Excel 報表下載 |
| **Realtime** | WebSocket 即時推送、產生器狀態、歷史資料查詢 |
| **Admin** | 系統日誌、資料庫狀態監控、系統概覽 |

#### 權限說明
- `admin`：全部權限
- `user`：可建立與維護自己的資料
- `viewer`：唯讀，僅能查詢與分析

#### WebSocket
`ws://<host>/api/v1/realtime/ws?token=<access_token>`
"""


async def _wait_for_database(retries: int = 30, delay: float = 2.0) -> None:
    """等待資料庫就緒（容器啟動順序保護）。"""
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(select(1))
            logger.info("資料庫連線成功")
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("資料庫尚未就緒（%d/%d）：%s", attempt, retries, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("無法連線至資料庫，請確認 DB 設定與容器狀態")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("啟動 %s v%s（%s）", settings.PROJECT_NAME, settings.VERSION, settings.ENVIRONMENT)
    await _wait_for_database()
    await seed_demo_data()
    await generator.start()
    try:
        yield
    finally:
        await generator.stop()
        await engine.dispose()
        logger.info("應用程式已關閉")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=DESCRIPTION,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms", "Content-Disposition"],
)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    general_limit=settings.RATE_LIMIT_GENERAL,
    login_limit=settings.RATE_LIMIT_LOGIN,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["System"], summary="服務資訊")
async def root() -> dict:
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
    }


@app.get("/health", tags=["System"], summary="健康檢查")
async def health() -> dict:
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "generator": "running" if generator.running else "stopped",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

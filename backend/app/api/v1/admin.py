"""系統管理 API（Admin 專用）：系統日誌、資料庫狀態、系統概覽。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, require_admin
from app.core.config import settings
from app.db.session import pool_status
from app.models.metric import MetricPoint
from app.models.record import DataRecord
from app.models.system_log import SystemLog
from app.models.user import User
from app.schemas.analytics import DatabaseStatus, SystemLogRead, TableStat
from app.schemas.common import Page
from app.services import log_service
from app.services.generator import generator
from app.services.ws_manager import manager

router = APIRouter(
    prefix="/admin",
    tags=["Admin 系統管理"],
    dependencies=[Depends(require_admin)],
)


@router.get("/logs", response_model=Page[SystemLogRead], summary="系統日誌查詢")
async def list_logs(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
    level: Annotated[str | None, Query(pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")] = None,
    keyword: str | None = None,
    user_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> Page[SystemLogRead]:
    logs, total = await log_service.list_logs(
        db,
        page=page,
        size=size,
        level=level,
        keyword=keyword,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
    )
    return Page.create([SystemLogRead.model_validate(log) for log in logs], total, page, size)


@router.get("/database", response_model=DatabaseStatus, summary="資料庫狀態監控")
async def database_status(db: DbSession) -> DatabaseStatus:
    tables: list[TableStat] = []
    for name, model in (
        ("users", User),
        ("data_records", DataRecord),
        ("metric_points", MetricPoint),
        ("system_logs", SystemLog),
    ):
        count = (await db.execute(select(func.count()).select_from(model))).scalar_one()
        tables.append(TableStat(table=name, rows=int(count)))

    server_time = (await db.execute(select(func.now()))).scalar_one()

    return DatabaseStatus(
        connected=True,
        dialect=db.bind.dialect.name if db.bind else "unknown",
        pool=pool_status(),
        tables=tables,
        server_time=server_time if isinstance(server_time, datetime) else None,
    )


@router.get("/overview", summary="系統概覽")
async def system_overview(db: DbSession) -> dict:
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    active_users = (
        await db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))
    ).scalar_one()
    total_records = (await db.execute(select(func.count()).select_from(DataRecord))).scalar_one()
    total_metrics = (await db.execute(select(func.count()).select_from(MetricPoint))).scalar_one()
    total_alerts = (
        await db.execute(
            select(func.count()).select_from(MetricPoint).where(MetricPoint.is_alert.is_(True))
        )
    ).scalar_one()

    return {
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "users": {"total": int(total_users), "active": int(active_users)},
        "records": int(total_records),
        "metrics": {"total": int(total_metrics), "alerts": int(total_alerts)},
        "realtime": {
            "generator_running": generator.running,
            "buffered": generator.buffered,
            "websocket_connections": manager.count,
            "total_generated": generator.total_generated,
            "total_persisted": generator.total_persisted,
        },
    }

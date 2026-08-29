"""系統日誌服務（寫入與查詢）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.db.session import AsyncSessionLocal
from app.models.system_log import SystemLog

logger = get_logger(__name__)


async def write_log(
    *,
    level: str,
    action: str,
    message: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    duration_ms: int | None = None,
    client_ip: str | None = None,
    user_id: int | None = None,
) -> None:
    """以獨立 Session 寫入日誌，寫入失敗不影響主要流程。"""
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                SystemLog(
                    level=level,
                    action=action,
                    message=message,
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    user_id=user_id,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 - 日誌失敗僅記錄於 stdout
        logger.warning("寫入系統日誌失敗", exc_info=True)


async def list_logs(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 50,
    level: str | None = None,
    keyword: str | None = None,
    user_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[SystemLog], int]:
    stmt = select(SystemLog)
    count_stmt = select(func.count()).select_from(SystemLog)

    conditions = []
    if level:
        conditions.append(SystemLog.level == level.upper())
    if keyword:
        pattern = f"%{keyword}%"
        conditions.append(or_(SystemLog.action.like(pattern), SystemLog.path.like(pattern)))
    if user_id is not None:
        conditions.append(SystemLog.user_id == user_id)
    if start_time is not None:
        conditions.append(SystemLog.created_at >= start_time)
    if end_time is not None:
        conditions.append(SystemLog.created_at <= end_time)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(SystemLog.id.desc()).offset((page - 1) * size).limit(size)
    logs = list((await db.execute(stmt)).scalars().all())
    return logs, total

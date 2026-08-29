"""資料分析業務邏輯（統計、聚合、趨勢）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.record import DataRecord
from app.schemas.analytics import CategoryAggregate, StatsSummary, TrendPoint

_MYSQL_FORMAT = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "month": "%Y-%m"}
_SQLITE_FORMAT = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "month": "%Y-%m"}


def _bucket_expression(granularity: str):
    """依資料庫方言產生時間分組欄位（仍為 ORM 表達式，非原生 SQL 字串執行）。"""
    granularity = granularity if granularity in _MYSQL_FORMAT else "day"
    if settings.is_sqlite:
        return func.strftime(_SQLITE_FORMAT[granularity], DataRecord.recorded_at)
    return func.date_format(DataRecord.recorded_at, _MYSQL_FORMAT[granularity])


def _apply_filters(
    stmt: Select,
    *,
    category: str | None,
    owner_id: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> Select:
    if category:
        stmt = stmt.where(DataRecord.category == category)
    if owner_id is not None:
        stmt = stmt.where(DataRecord.owner_id == owner_id)
    if start_time is not None:
        stmt = stmt.where(DataRecord.recorded_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(DataRecord.recorded_at <= end_time)
    return stmt


async def summary(
    db: AsyncSession,
    *,
    category: str | None = None,
    owner_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> StatsSummary:
    stmt = select(
        func.count(DataRecord.id),
        func.sum(DataRecord.value),
        func.avg(DataRecord.value),
        func.min(DataRecord.value),
        func.max(DataRecord.value),
        func.min(DataRecord.recorded_at),
        func.max(DataRecord.recorded_at),
    )
    stmt = _apply_filters(
        stmt, category=category, owner_id=owner_id, start_time=start_time, end_time=end_time
    )
    count, total, average, minimum, maximum, first_at, last_at = (
        await db.execute(stmt)
    ).one()

    return StatsSummary(
        count=count or 0,
        total=float(total) if total is not None else None,
        average=round(float(average), 4) if average is not None else None,
        minimum=float(minimum) if minimum is not None else None,
        maximum=float(maximum) if maximum is not None else None,
        start_time=first_at,
        end_time=last_at,
    )


async def aggregate_by_category(
    db: AsyncSession,
    *,
    owner_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[CategoryAggregate]:
    stmt = select(
        DataRecord.category,
        func.count(DataRecord.id),
        func.sum(DataRecord.value),
        func.avg(DataRecord.value),
        func.min(DataRecord.value),
        func.max(DataRecord.value),
    ).group_by(DataRecord.category)
    stmt = _apply_filters(
        stmt, category=None, owner_id=owner_id, start_time=start_time, end_time=end_time
    )
    stmt = stmt.order_by(func.sum(DataRecord.value).desc())

    rows = (await db.execute(stmt)).all()
    return [
        CategoryAggregate(
            category=row[0],
            count=row[1],
            total=float(row[2] or 0),
            average=round(float(row[3] or 0), 4),
            minimum=float(row[4] or 0),
            maximum=float(row[5] or 0),
        )
        for row in rows
    ]


async def trend(
    db: AsyncSession,
    *,
    granularity: str = "day",
    category: str | None = None,
    owner_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[TrendPoint]:
    bucket = _bucket_expression(granularity).label("bucket")
    stmt = select(
        bucket,
        func.count(DataRecord.id),
        func.sum(DataRecord.value),
        func.avg(DataRecord.value),
    ).group_by(bucket)
    stmt = _apply_filters(
        stmt, category=category, owner_id=owner_id, start_time=start_time, end_time=end_time
    )
    stmt = stmt.order_by(bucket.asc())

    rows = (await db.execute(stmt)).all()
    return [
        TrendPoint(
            bucket=str(row[0]),
            count=row[1],
            total=float(row[2] or 0),
            average=round(float(row[3] or 0), 4),
        )
        for row in rows
    ]

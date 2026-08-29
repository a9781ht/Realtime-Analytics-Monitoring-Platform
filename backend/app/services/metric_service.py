"""即時監控歷史資料查詢服務。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metric import MetricPoint


async def list_metrics(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 100,
    sensor_id: str | None = None,
    metric_name: str | None = None,
    only_alert: bool = False,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    order: str = "desc",
) -> tuple[list[MetricPoint], int]:
    stmt = select(MetricPoint)
    count_stmt = select(func.count()).select_from(MetricPoint)

    conditions = []
    if sensor_id:
        conditions.append(MetricPoint.sensor_id == sensor_id)
    if metric_name:
        conditions.append(MetricPoint.metric_name == metric_name)
    if only_alert:
        conditions.append(MetricPoint.is_alert.is_(True))
    if start_time is not None:
        conditions.append(MetricPoint.generated_at >= start_time)
    if end_time is not None:
        conditions.append(MetricPoint.generated_at <= end_time)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()
    column = MetricPoint.generated_at
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
    stmt = stmt.offset((page - 1) * size).limit(size)

    return list((await db.execute(stmt)).scalars().all()), total


async def sensor_summary(
    db: AsyncSession,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[dict]:
    stmt = select(
        MetricPoint.sensor_id,
        MetricPoint.metric_name,
        func.count(MetricPoint.id),
        func.avg(MetricPoint.value),
        func.min(MetricPoint.value),
        func.max(MetricPoint.value),
        func.sum(cast(MetricPoint.is_alert, Integer)),
    ).group_by(MetricPoint.sensor_id, MetricPoint.metric_name)

    if start_time is not None:
        stmt = stmt.where(MetricPoint.generated_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(MetricPoint.generated_at <= end_time)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "sensor_id": row[0],
            "metric_name": row[1],
            "count": row[2],
            "average": round(float(row[3] or 0), 3),
            "minimum": float(row[4] or 0),
            "maximum": float(row[5] or 0),
            "alerts": int(row[6] or 0),
        }
        for row in rows
    ]

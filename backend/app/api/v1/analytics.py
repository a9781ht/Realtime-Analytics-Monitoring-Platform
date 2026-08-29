"""資料分析 API：統計、分類聚合、趨勢、Excel 匯出。"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession
from app.schemas.analytics import CategoryAggregate, StatsSummary, TrendPoint
from app.services import analytics_service, record_service

router = APIRouter(prefix="/analytics", tags=["Analytics 資料分析"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/summary", response_model=StatsSummary, summary="統計摘要（總計 / 平均 / 最大 / 最小）")
async def get_summary(
    db: DbSession,
    _: CurrentUser,
    category: str | None = None,
    owner_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> StatsSummary:
    return await analytics_service.summary(
        db, category=category, owner_id=owner_id, start_time=start_time, end_time=end_time
    )


@router.get("/categories", response_model=list[CategoryAggregate], summary="分類資料聚合")
async def get_category_aggregate(
    db: DbSession,
    _: CurrentUser,
    owner_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[CategoryAggregate]:
    return await analytics_service.aggregate_by_category(
        db, owner_id=owner_id, start_time=start_time, end_time=end_time
    )


@router.get("/trend", response_model=list[TrendPoint], summary="時間趨勢分析")
async def get_trend(
    db: DbSession,
    _: CurrentUser,
    granularity: Annotated[str, Query(pattern="^(hour|day|month)$")] = "day",
    category: str | None = None,
    owner_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[TrendPoint]:
    return await analytics_service.trend(
        db,
        granularity=granularity,
        category=category,
        owner_id=owner_id,
        start_time=start_time,
        end_time=end_time,
    )


def _build_workbook(
    records: list[dict], stats: dict, categories: list[dict], trends: list[dict]
) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(records).to_excel(writer, sheet_name="資料明細", index=False)
        pd.DataFrame([stats]).to_excel(writer, sheet_name="統計摘要", index=False)
        pd.DataFrame(categories).to_excel(writer, sheet_name="分類聚合", index=False)
        pd.DataFrame(trends).to_excel(writer, sheet_name="趨勢分析", index=False)
    return buffer.getvalue()


@router.get("/export", summary="下載分析報表（Excel）", response_class=StreamingResponse)
async def export_excel(
    db: DbSession,
    _: CurrentUser,
    category: str | None = None,
    owner_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    granularity: Annotated[str, Query(pattern="^(hour|day|month)$")] = "day",
    limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
) -> StreamingResponse:
    records, _total = await record_service.list_records(
        db,
        page=1,
        size=limit,
        category=category,
        owner_id=owner_id,
        start_time=start_time,
        end_time=end_time,
        sort_by="recorded_at",
        order="desc",
    )
    stats = await analytics_service.summary(
        db, category=category, owner_id=owner_id, start_time=start_time, end_time=end_time
    )
    categories = await analytics_service.aggregate_by_category(
        db, owner_id=owner_id, start_time=start_time, end_time=end_time
    )
    trends = await analytics_service.trend(
        db,
        granularity=granularity,
        category=category,
        owner_id=owner_id,
        start_time=start_time,
        end_time=end_time,
    )

    rows = [
        {
            "id": record.id,
            "title": record.title,
            "value": record.value,
            "category": record.category,
            "description": record.description,
            "recorded_at": record.recorded_at,
            "owner": record.owner.username if record.owner else None,
        }
        for record in records
    ]

    content = await run_in_threadpool(
        _build_workbook,
        rows,
        stats.model_dump(),
        [item.model_dump() for item in categories],
        [item.model_dump() for item in trends],
    )
    filename = f"analytics_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

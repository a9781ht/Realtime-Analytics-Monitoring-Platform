"""即時監控 API：WebSocket 推送、產生器狀態、歷史資料查詢。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.api.deps import CurrentUser, DbSession, get_ws_user, require_admin
from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.metric import GeneratorStatus, MetricPointRead
from app.services import metric_service
from app.services.generator import generator
from app.services.ws_manager import manager

logger = get_logger(__name__)
router = APIRouter(prefix="/realtime", tags=["Realtime 即時監控"])


@router.websocket("/ws")
async def realtime_websocket(
    websocket: WebSocket,
    user: Annotated[User | None, Depends(get_ws_user)],
) -> None:
    """即時資料推送通道。

    連線方式：`ws://<host>/api/v1/realtime/ws?token=<access_token>`

    伺服器推送訊息格式：
    ```json
    {"type": "metrics", "timestamp": "...", "payload": [{"sensor_id": "...", "value": 1.0, ...}]}
    ```
    """
    if user is None:  # 認證失敗，get_ws_user 已關閉連線
        return

    await manager.connect(websocket, user.username)
    await manager.send_personal(
        websocket,
        json.dumps(
            {
                "type": "welcome",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "username": user.username,
                    "role": user.role.value,
                    "threshold_high": settings.ALERT_THRESHOLD_HIGH,
                    "threshold_low": settings.ALERT_THRESHOLD_LOW,
                },
            },
            ensure_ascii=False,
        ),
    )

    try:
        while True:
            text = await websocket.receive_text()
            if text.strip().lower() == "ping":
                await manager.send_personal(
                    websocket,
                    json.dumps(
                        {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}
                    ),
                )
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        logger.exception("WebSocket 發生錯誤")
        await manager.disconnect(websocket)


@router.get("/status", response_model=GeneratorStatus, summary="即時資料產生器狀態")
async def get_status(_: CurrentUser) -> GeneratorStatus:
    return GeneratorStatus(
        enabled=settings.GENERATOR_ENABLED,
        running=generator.running,
        interval_seconds=settings.GENERATOR_INTERVAL_SECONDS,
        batch_size=settings.GENERATOR_BATCH_SIZE,
        buffered=generator.buffered,
        total_generated=generator.total_generated,
        total_persisted=generator.total_persisted,
        last_flush_at=generator.last_flush_at,
        active_connections=manager.count,
        threshold_high=settings.ALERT_THRESHOLD_HIGH,
        threshold_low=settings.ALERT_THRESHOLD_LOW,
    )


@router.get("/latest", summary="取得最新一批即時資料（WebSocket 備援）")
async def get_latest(_: CurrentUser) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": generator.latest,
    }


@router.get(
    "/metrics",
    response_model=Page[MetricPointRead],
    summary="即時資料歷史查詢（Admin）",
    dependencies=[Depends(require_admin)],
)
async def list_metrics(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 100,
    sensor_id: str | None = None,
    metric_name: str | None = None,
    only_alert: bool = False,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[MetricPointRead]:
    metrics, total = await metric_service.list_metrics(
        db,
        page=page,
        size=size,
        sensor_id=sensor_id,
        metric_name=metric_name,
        only_alert=only_alert,
        start_time=start_time,
        end_time=end_time,
        order=order,
    )
    return Page.create(
        [MetricPointRead.model_validate(metric) for metric in metrics], total, page, size
    )


@router.get(
    "/metrics/summary",
    summary="各感測器統計摘要（Admin）",
    dependencies=[Depends(require_admin)],
)
async def metrics_summary(
    db: DbSession,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[dict]:
    return await metric_service.sensor_summary(db, start_time=start_time, end_time=end_time)


@router.post(
    "/flush",
    response_model=Message,
    summary="立即將緩衝資料寫入資料庫（Admin）",
    dependencies=[Depends(require_admin)],
)
async def flush_buffer() -> Message:
    written = await generator.flush()
    return Message(message=f"已批次寫入 {written} 筆即時資料")

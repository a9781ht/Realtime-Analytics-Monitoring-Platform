"""即時監控資料 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AlertLevel


class MetricPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sensor_id: str
    metric_name: str
    value: float
    unit: str
    is_alert: bool
    alert_level: AlertLevel
    generated_at: datetime


class MetricPointMessage(BaseModel):
    """WebSocket 推送的單筆資料（尚未寫入資料庫時沒有 id）。"""

    sensor_id: str
    metric_name: str
    value: float
    unit: str
    is_alert: bool
    alert_level: AlertLevel
    generated_at: datetime


class RealtimeEnvelope(BaseModel):
    """WebSocket 訊息封包。"""

    type: str = Field(..., examples=["metrics", "pong", "error"])
    timestamp: datetime
    payload: list[MetricPointMessage] | dict | None = None


class GeneratorStatus(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: float
    batch_size: int
    buffered: int
    total_generated: int
    total_persisted: int
    last_flush_at: datetime | None
    active_connections: int
    threshold_high: float
    threshold_low: float

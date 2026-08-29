"""即時監控資料（由產生器批次寫入）ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AlertLevel


class MetricPoint(Base):
    """單一即時資料點。"""

    __tablename__ = "metric_points"
    __table_args__ = (
        Index("ix_metric_points_sensor_generated", "sensor_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    is_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    alert_level: Mapped[AlertLevel] = mapped_column(
        SAEnum(AlertLevel, native_enum=False, length=20), default=AlertLevel.NORMAL, nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MetricPoint {self.sensor_id} {self.value} alert={self.is_alert}>"

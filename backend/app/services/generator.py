"""即時資料產生器。

功能：
1. 每 N 秒模擬產生感測器資料（隨機值）。
2. 依閾值標記異常告警等級。
3. 透過 WebSocket 廣播給所有訂閱者。
4. 以緩衝區暫存，達到「時間間隔」或「筆數門檻」時，使用 ORM 批次寫入 MariaDB。
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.session import AsyncSessionLocal
from app.models.enums import AlertLevel
from app.models.metric import MetricPoint
from app.services.ws_manager import manager

logger = get_logger(__name__)

SENSORS: list[dict[str, object]] = [
    {"sensor_id": "SENSOR-01", "metric_name": "temperature", "unit": "°C", "base": 55.0, "swing": 40.0},
    {"sensor_id": "SENSOR-02", "metric_name": "humidity", "unit": "%", "base": 50.0, "swing": 35.0},
    {"sensor_id": "SENSOR-03", "metric_name": "pressure", "unit": "kPa", "base": 60.0, "swing": 30.0},
    {"sensor_id": "SENSOR-04", "metric_name": "vibration", "unit": "mm/s", "base": 45.0, "swing": 45.0},
    {"sensor_id": "SENSOR-05", "metric_name": "power", "unit": "kW", "base": 65.0, "swing": 35.0},
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def classify(value: float) -> tuple[bool, AlertLevel]:
    """依據閾值判斷告警等級。"""
    high = settings.ALERT_THRESHOLD_HIGH
    low = settings.ALERT_THRESHOLD_LOW
    if value >= high + 5 or value <= max(low - 5, 0):
        return True, AlertLevel.CRITICAL
    if value >= high or value <= low:
        return True, AlertLevel.WARNING
    return False, AlertLevel.NORMAL


class RealtimeGenerator:
    """背景資料產生器（單例）。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._flush_task: asyncio.Task | None = None
        self._buffer: list[dict] = []
        self._lock = asyncio.Lock()
        self._running = False
        self.total_generated = 0
        self.total_persisted = 0
        self.last_flush_at: datetime | None = None
        self.latest: list[dict] = []

    # ---------- 生命週期 ----------
    async def start(self) -> None:
        if self._running or not settings.GENERATOR_ENABLED:
            return
        self._running = True
        self._task = asyncio.create_task(self._generate_loop(), name="metric-generator")
        self._flush_task = asyncio.create_task(self._flush_loop(), name="metric-flusher")
        logger.info("即時資料產生器已啟動")

    async def stop(self) -> None:
        self._running = False
        for task in (self._task, self._flush_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:  # pragma: no cover
                    pass
        await self.flush()
        logger.info("即時資料產生器已停止")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def buffered(self) -> int:
        return len(self._buffer)

    # ---------- 主要流程 ----------
    def _generate_batch(self) -> list[dict]:
        timestamp = _now()
        batch: list[dict] = []
        sample_size = min(settings.GENERATOR_BATCH_SIZE, len(SENSORS))
        for sensor in random.sample(SENSORS, sample_size):
            base = float(sensor["base"])  # type: ignore[arg-type]
            swing = float(sensor["swing"])  # type: ignore[arg-type]
            value = round(max(0.0, random.gauss(base, swing / 3)), 2)
            is_alert, level = classify(value)
            batch.append(
                {
                    "sensor_id": sensor["sensor_id"],
                    "metric_name": sensor["metric_name"],
                    "unit": sensor["unit"],
                    "value": value,
                    "is_alert": is_alert,
                    "alert_level": level.value,
                    "generated_at": timestamp.isoformat(),
                }
            )
        return batch

    async def _generate_loop(self) -> None:
        while self._running:
            try:
                batch = self._generate_batch()
                self.total_generated += len(batch)
                self.latest = batch

                async with self._lock:
                    self._buffer.extend(batch)
                    should_flush = len(self._buffer) >= settings.GENERATOR_FLUSH_SIZE

                await manager.broadcast(
                    json.dumps(
                        {"type": "metrics", "timestamp": _now().isoformat(), "payload": batch},
                        ensure_ascii=False,
                    )
                )

                if should_flush:  # 條件觸發：緩衝筆數達門檻
                    await self.flush()

                await asyncio.sleep(settings.GENERATOR_INTERVAL_SECONDS)
            except asyncio.CancelledError:  # pragma: no cover
                raise
            except Exception:  # noqa: BLE001
                logger.exception("資料產生迴圈發生錯誤")
                await asyncio.sleep(1)

    async def _flush_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(settings.GENERATOR_FLUSH_INTERVAL)
                await self.flush()  # 定期觸發
            except asyncio.CancelledError:  # pragma: no cover
                raise
            except Exception:  # noqa: BLE001
                logger.exception("批次寫入迴圈發生錯誤")

    async def flush(self) -> int:
        """將緩衝區資料以 ORM 批次寫入資料庫。"""
        async with self._lock:
            if not self._buffer:
                return 0
            pending, self._buffer = self._buffer, []

        rows = [
            MetricPoint(
                sensor_id=item["sensor_id"],
                metric_name=item["metric_name"],
                unit=item["unit"],
                value=item["value"],
                is_alert=item["is_alert"],
                alert_level=AlertLevel(item["alert_level"]),
                generated_at=datetime.fromisoformat(item["generated_at"]),
            )
            for item in pending
        ]

        try:
            async with AsyncSessionLocal() as session:
                session.add_all(rows)
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("批次寫入資料庫失敗，將丟棄 %d 筆暫存資料", len(rows))
            return 0

        self.total_persisted += len(rows)
        self.last_flush_at = _now()
        logger.info("批次寫入 %d 筆即時資料", len(rows))
        return len(rows)


generator = RealtimeGenerator()

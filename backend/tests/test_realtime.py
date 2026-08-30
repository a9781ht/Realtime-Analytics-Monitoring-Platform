"""即時監控模組測試：告警判定、資料產生、WebSocket 管理與歷史查詢權限。"""

from __future__ import annotations

import json

from httpx import AsyncClient

from app.api.deps import get_ws_user
from app.core.config import settings
from app.models.enums import AlertLevel
from app.services.generator import RealtimeGenerator, classify
from app.services.ws_manager import ConnectionManager


class FakeWebSocket:
    """最小 WebSocket 替身，用於測試連線管理與認證流程。"""

    def __init__(self, fail_on_send: bool = False) -> None:
        self.sent: list[str] = []
        self.accepted = False
        self.close_code: int | None = None
        self._fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, message: str) -> None:
        if self._fail_on_send:
            raise RuntimeError("connection closed")
        self.sent.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_code = code


# ---------- 告警判定與資料產生 ----------


def test_classify_flags_values_over_threshold() -> None:
    high = settings.ALERT_THRESHOLD_HIGH
    low = settings.ALERT_THRESHOLD_LOW

    assert classify(high) == (True, AlertLevel.WARNING)
    assert classify(high + 10) == (True, AlertLevel.CRITICAL)
    assert classify(low) == (True, AlertLevel.WARNING)
    assert classify((high + low) / 2) == (False, AlertLevel.NORMAL)


def test_generated_batch_shape_and_alert_consistency() -> None:
    generator = RealtimeGenerator()
    batch = generator._generate_batch()

    assert len(batch) == settings.GENERATOR_BATCH_SIZE
    for item in batch:
        assert {"sensor_id", "metric_name", "unit", "value", "is_alert", "alert_level"} <= set(item)
        expected_alert, expected_level = classify(item["value"])
        assert item["is_alert"] is expected_alert
        assert item["alert_level"] == expected_level.value


async def test_flush_with_empty_buffer_writes_nothing() -> None:
    generator = RealtimeGenerator()
    assert generator.buffered == 0
    assert await generator.flush() == 0
    assert generator.total_persisted == 0


# ---------- WebSocket 連線管理 ----------


async def test_connection_manager_tracks_and_broadcasts() -> None:
    manager = ConnectionManager()
    alice, bob = FakeWebSocket(), FakeWebSocket()

    await manager.connect(alice, "alice")
    await manager.connect(bob, "bob")
    assert alice.accepted and bob.accepted
    assert manager.count == 2

    await manager.broadcast(json.dumps({"type": "metrics"}))
    assert len(alice.sent) == 1 and len(bob.sent) == 1

    await manager.disconnect(alice)
    assert manager.count == 1


async def test_connection_manager_prunes_dead_connections() -> None:
    manager = ConnectionManager()
    healthy, broken = FakeWebSocket(), FakeWebSocket(fail_on_send=True)
    await manager.connect(healthy, "healthy")
    await manager.connect(broken, "broken")

    await manager.broadcast("ping")

    assert manager.count == 1
    assert healthy.sent == ["ping"]


async def test_ws_auth_rejects_missing_token() -> None:
    websocket = FakeWebSocket()
    assert await get_ws_user(websocket, db=None, token=None) is None
    assert websocket.close_code == 1008


async def test_ws_auth_rejects_invalid_token() -> None:
    websocket = FakeWebSocket()
    assert await get_ws_user(websocket, db=None, token="not-a-jwt") is None
    assert websocket.close_code == 1008


# ---------- REST 端點與權限 ----------


async def test_generator_status_visible_to_any_user(
    client: AsyncClient, registered_user: dict
) -> None:
    response = await client.get("/api/v1/realtime/status", headers=registered_user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["interval_seconds"] == settings.GENERATOR_INTERVAL_SECONDS
    assert body["threshold_high"] == settings.ALERT_THRESHOLD_HIGH


async def test_latest_endpoint_available_to_viewer(client: AsyncClient, viewer_user: dict) -> None:
    response = await client.get("/api/v1/realtime/latest", headers=viewer_user["headers"])
    assert response.status_code == 200
    assert "payload" in response.json()


async def test_metrics_history_is_admin_only(
    client: AsyncClient, admin_user: dict, registered_user: dict, viewer_user: dict
) -> None:
    assert (
        await client.get("/api/v1/realtime/metrics", headers=admin_user["headers"])
    ).status_code == 200
    assert (
        await client.get("/api/v1/realtime/metrics", headers=registered_user["headers"])
    ).status_code == 403
    assert (
        await client.get("/api/v1/realtime/metrics", headers=viewer_user["headers"])
    ).status_code == 403


async def test_metrics_summary_is_admin_only(
    client: AsyncClient, admin_user: dict, registered_user: dict
) -> None:
    assert (
        await client.get("/api/v1/realtime/metrics/summary", headers=admin_user["headers"])
    ).status_code == 200
    assert (
        await client.get("/api/v1/realtime/metrics/summary", headers=registered_user["headers"])
    ).status_code == 403


async def test_flush_is_admin_only(
    client: AsyncClient, admin_user: dict, registered_user: dict
) -> None:
    assert (
        await client.post("/api/v1/realtime/flush", headers=registered_user["headers"])
    ).status_code == 403
    assert (
        await client.post("/api/v1/realtime/flush", headers=admin_user["headers"])
    ).status_code == 200


async def test_realtime_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/realtime/status")).status_code == 401
    assert (await client.get("/api/v1/realtime/metrics")).status_code == 401

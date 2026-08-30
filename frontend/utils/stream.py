"""WebSocket 即時資料串流用戶端（背景執行緒）。"""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime

import websocket


class MetricStream:
    """在背景執行緒接收 WebSocket 推送資料，主執行緒定期讀取緩衝區。"""

    def __init__(self, url: str, maxlen: int = 900) -> None:
        # 主執行緒可隨時更新 url（token 換發後），背景執行緒於下次重連時採用
        self.url = url
        self.points: deque[dict] = deque(maxlen=maxlen)
        self.alerts: deque[dict] = deque(maxlen=100)
        self.connected = False
        self.error: str | None = None
        self.received = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- 生命週期 ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="metric-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.connected = False

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---------- 接收迴圈 ----------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                ws = websocket.create_connection(self.url, timeout=10)
                self.connected = True
                self.error = None
                while not self._stop_event.is_set():
                    raw = ws.recv()
                    if not raw:
                        continue
                    self._handle(raw)
                ws.close()
            except Exception as exc:  # noqa: BLE001
                self.connected = False
                self.error = str(exc)
                if self._stop_event.wait(3):
                    break
        self.connected = False

    def _handle(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        if message.get("type") != "metrics":
            return

        for item in message.get("payload", []):
            item["generated_at"] = _parse_time(item.get("generated_at"))
            self.points.append(item)
            self.received += 1
            if item.get("is_alert"):
                self.alerts.appendleft(item)

    # ---------- 資料存取 ----------
    def snapshot(self) -> list[dict]:
        return list(self.points)

    def alert_list(self) -> list[dict]:
        return list(self.alerts)


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()

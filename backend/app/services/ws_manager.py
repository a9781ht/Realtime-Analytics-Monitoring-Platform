"""WebSocket 連線管理員：負責註冊、移除與廣播訊息。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ConnectionManager:
    active: dict[WebSocket, str] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def connect(self, websocket: WebSocket, username: str) -> None:
        await websocket.accept()
        async with self._lock:
            self.active[websocket] = username
        logger.info("WebSocket 連線建立: %s（目前連線數 %d）", username, len(self.active))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            username = self.active.pop(websocket, None)
        if username:
            logger.info("WebSocket 連線關閉: %s（剩餘連線數 %d）", username, len(self.active))

    @property
    def count(self) -> int:
        return len(self.active)

    async def send_personal(self, websocket: WebSocket, message: str) -> None:
        try:
            await websocket.send_text(message)
        except Exception:  # noqa: BLE001
            await self.disconnect(websocket)

    async def broadcast(self, message: str) -> None:
        """廣播訊息，對於失效連線自動移除。"""
        async with self._lock:
            targets = list(self.active.keys())

        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_text(message)
            except Exception:  # noqa: BLE001
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self.active.pop(websocket, None)


manager = ConnectionManager()

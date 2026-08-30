"""後端 API 用戶端封裝。"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
WS_BASE_URL = os.getenv("WS_BASE_URL", API_BASE_URL.replace("http", "ws")).rstrip("/")
API_PREFIX = "/api/v1"
TIMEOUT = 20


class APIError(Exception):
    """API 呼叫失敗。"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class APIClient:
    def __init__(
        self,
        token: str | None = None,
        refresh_token: str | None = None,
        on_token_refresh: Callable[[dict], None] | None = None,
    ) -> None:
        self.token = token
        self.refresh_token = refresh_token
        self.base = f"{API_BASE_URL}{API_PREFIX}"
        self._on_token_refresh = on_token_refresh

    # ---------- 內部工具 ----------
    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    def _try_refresh(self) -> bool:
        """以 refresh token 換發新的 access token，成功則回傳 True。"""
        if not self.refresh_token:
            return False
        try:
            response = requests.post(
                f"{self.base}/auth/refresh",
                json={"refresh_token": self.refresh_token},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            return False
        if response.status_code >= 400:
            return False
        try:
            tokens = response.json()
        except ValueError:
            return False

        self.token = tokens.get("access_token")
        # 後端換發時會撤銷舊的 refresh token，必須同步更新
        self.refresh_token = tokens.get("refresh_token")
        if not self.token:
            return False
        if self._on_token_refresh:
            self._on_token_refresh(tokens)
        return True

    def _request(self, method: str, path: str, allow_refresh: bool = True, **kwargs: Any) -> Any:
        url = f"{self.base}{path}"
        timeout = kwargs.pop("timeout", TIMEOUT)
        try:
            response = requests.request(
                method, url, headers=self._headers(kwargs.pop("headers", None)),
                timeout=timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise APIError(f"無法連線至後端服務：{exc}") from exc

        if response.status_code == 401 and allow_refresh and self._try_refresh():
            return self._request(method, path, allow_refresh=False, timeout=timeout, **kwargs)

        if response.status_code >= 400:
            message = response.text
            try:
                body = response.json()
                message = body.get("error", {}).get("message") or body.get("detail") or message
            except ValueError:
                pass
            raise APIError(str(message), response.status_code)

        if response.headers.get("Content-Type", "").startswith("application/json"):
            return response.json()
        return response.content

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None, **kwargs: Any) -> Any:
        return self._request("POST", path, json=json, **kwargs)

    def patch(self, path: str, json: dict | None = None) -> Any:
        return self._request("PATCH", path, json=json)

    def put(self, path: str, json: dict | None = None) -> Any:
        return self._request("PUT", path, json=json)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def download(self, path: str, params: dict | None = None) -> bytes:
        return self._request("GET", path, params=params, timeout=120)

    # ---------- 認證 ----------
    def login(self, username: str, password: str) -> dict:
        return self.post("/auth/login", {"username": username, "password": password})

    def register(self, payload: dict) -> dict:
        return self.post("/auth/register", payload)

    def me(self) -> dict:
        return self.get("/auth/me")

    def logout(self) -> dict:
        return self.post("/auth/logout")

    # ---------- WebSocket ----------
    def websocket_url(self) -> str:
        return f"{WS_BASE_URL}{API_PREFIX}/realtime/ws?token={self.token}"

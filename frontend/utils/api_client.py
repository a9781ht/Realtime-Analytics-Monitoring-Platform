"""後端 API 用戶端封裝。"""

from __future__ import annotations

import os
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
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self.base = f"{API_BASE_URL}{API_PREFIX}"

    # ---------- 內部工具 ----------
    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base}{path}"
        try:
            response = requests.request(
                method, url, headers=self._headers(kwargs.pop("headers", None)),
                timeout=TIMEOUT, **kwargs
            )
        except requests.RequestException as exc:
            raise APIError(f"無法連線至後端服務：{exc}") from exc

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
        url = f"{self.base}{path}"
        try:
            response = requests.get(url, headers=self._headers(), params=params, timeout=120)
        except requests.RequestException as exc:
            raise APIError(f"下載失敗：{exc}") from exc
        if response.status_code >= 400:
            raise APIError("報表下載失敗", response.status_code)
        return response.content

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

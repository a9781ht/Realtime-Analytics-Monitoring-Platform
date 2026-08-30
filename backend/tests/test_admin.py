"""系統管理模組測試：使用者管理、系統日誌、資料庫狀態監控。"""

from __future__ import annotations

from httpx import AsyncClient


async def test_admin_lists_all_users(
    client: AsyncClient, admin_user: dict, registered_user: dict
) -> None:
    response = await client.get("/api/v1/users", headers=admin_user["headers"])
    assert response.status_code == 200
    usernames = {item["username"] for item in response.json()["items"]}
    assert {"root", "tester"} <= usernames


async def test_admin_updates_user_role(
    client: AsyncClient, admin_user: dict, registered_user: dict
) -> None:
    listing = await client.get(
        "/api/v1/users", headers=admin_user["headers"], params={"keyword": "tester"}
    )
    target_id = listing.json()["items"][0]["id"]

    response = await client.patch(
        f"/api/v1/users/{target_id}/role",
        headers=admin_user["headers"],
        json={"role": "viewer"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


async def test_admin_can_deactivate_user(
    client: AsyncClient, admin_user: dict, registered_user: dict
) -> None:
    listing = await client.get(
        "/api/v1/users", headers=admin_user["headers"], params={"keyword": "tester"}
    )
    target_id = listing.json()["items"][0]["id"]

    response = await client.patch(
        f"/api/v1/users/{target_id}/role",
        headers=admin_user["headers"],
        json={"role": "user", "is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # 帳號停用後既有 token 應立即失效
    assert (
        await client.get("/api/v1/auth/me", headers=registered_user["headers"])
    ).status_code == 401


async def test_system_logs_query(client: AsyncClient, admin_user: dict) -> None:
    response = await client.get(
        "/api/v1/admin/logs", headers=admin_user["headers"], params={"level": "INFO"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "meta" in body
    assert all(item["level"] == "INFO" for item in body["items"])


async def test_system_logs_reject_invalid_level(client: AsyncClient, admin_user: dict) -> None:
    response = await client.get(
        "/api/v1/admin/logs", headers=admin_user["headers"], params={"level": "TRACE"}
    )
    assert response.status_code == 422


async def test_database_status_monitoring(client: AsyncClient, admin_user: dict) -> None:
    response = await client.get("/api/v1/admin/database", headers=admin_user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    tables = {item["table"] for item in body["tables"]}
    assert {"users", "data_records", "metric_points", "system_logs"} <= tables


async def test_system_overview(client: AsyncClient, admin_user: dict) -> None:
    response = await client.get("/api/v1/admin/overview", headers=admin_user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["users"]["total"] >= 1
    assert "realtime" in body


async def test_admin_endpoints_forbidden_for_user(
    client: AsyncClient, registered_user: dict
) -> None:
    headers = registered_user["headers"]
    assert (await client.get("/api/v1/admin/logs", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/admin/database", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/admin/overview", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/users", headers=headers)).status_code == 403


async def test_admin_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/admin/logs")).status_code == 401
    assert (await client.get("/api/v1/admin/database")).status_code == 401

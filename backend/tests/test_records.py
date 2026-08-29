"""資料記錄 CRUD 與權限測試。"""

from __future__ import annotations

from httpx import AsyncClient


async def _create_record(client: AsyncClient, headers: dict, title: str = "溫度資料") -> dict:
    response = await client.post(
        "/api/v1/records",
        headers=headers,
        json={"title": title, "value": 36.5, "category": "temperature", "description": "測試"},
    )
    assert response.status_code == 201
    return response.json()


async def test_create_and_list_records(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    created = await _create_record(client, headers)
    assert created["title"] == "溫度資料"

    listing = await client.get("/api/v1/records", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["owner_username"] == "tester"


async def test_update_and_delete_record(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    created = await _create_record(client, headers)

    updated = await client.patch(
        f"/api/v1/records/{created['id']}", headers=headers, json={"value": 99.9}
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == 99.9

    deleted = await client.delete(f"/api/v1/records/{created['id']}", headers=headers)
    assert deleted.status_code == 200
    assert (await client.get(f"/api/v1/records/{created['id']}", headers=headers)).status_code == 404


async def test_other_user_cannot_modify(client: AsyncClient, registered_user: dict) -> None:
    created = await _create_record(client, registered_user["headers"])

    await client.post(
        "/api/v1/auth/register",
        json={"username": "carol", "email": "carol@example.com", "password": "Carol@1234"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"username": "carol", "password": "Carol@1234"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.patch(
        f"/api/v1/records/{created['id']}", headers=other_headers, json={"value": 1}
    )
    assert response.status_code == 403


async def test_bulk_import_json(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    response = await client.post(
        "/api/v1/records/bulk",
        headers=headers,
        json={
            "items": [
                {"title": "批次 1", "value": 10, "category": "power"},
                {"title": "批次 2", "value": 20, "category": "power"},
            ]
        },
    )
    assert response.status_code == 201
    assert response.json()["inserted"] == 2


async def test_analytics_summary(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _create_record(client, headers, "A")
    await _create_record(client, headers, "B")

    response = await client.get("/api/v1/analytics/summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["maximum"] == 36.5


async def test_admin_only_endpoint_forbidden(client: AsyncClient, registered_user: dict) -> None:
    response = await client.get("/api/v1/admin/logs", headers=registered_user["headers"])
    assert response.status_code == 403

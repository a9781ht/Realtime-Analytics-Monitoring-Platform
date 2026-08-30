"""角色權限測試：Viewer 唯讀、Admin 可跨使用者操作、Token 型別檢查。"""

from __future__ import annotations

from httpx import AsyncClient

RECORD_PAYLOAD = {"title": "權限測試", "value": 12.5, "category": "power"}


async def test_viewer_cannot_create_record(client: AsyncClient, viewer_user: dict) -> None:
    response = await client.post(
        "/api/v1/records", headers=viewer_user["headers"], json=RECORD_PAYLOAD
    )
    assert response.status_code == 403


async def test_viewer_can_read_records(
    client: AsyncClient, viewer_user: dict, registered_user: dict
) -> None:
    await client.post("/api/v1/records", headers=registered_user["headers"], json=RECORD_PAYLOAD)

    response = await client.get("/api/v1/records", headers=viewer_user["headers"])
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1


async def test_viewer_cannot_modify_or_delete(
    client: AsyncClient, viewer_user: dict, registered_user: dict
) -> None:
    created = await client.post(
        "/api/v1/records", headers=registered_user["headers"], json=RECORD_PAYLOAD
    )
    record_id = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/records/{record_id}", headers=viewer_user["headers"], json={"value": 1}
    )
    assert patched.status_code == 403

    deleted = await client.delete(
        f"/api/v1/records/{record_id}", headers=viewer_user["headers"]
    )
    assert deleted.status_code == 403


async def test_viewer_cannot_bulk_import(client: AsyncClient, viewer_user: dict) -> None:
    response = await client.post(
        "/api/v1/records/bulk",
        headers=viewer_user["headers"],
        json={"items": [RECORD_PAYLOAD]},
    )
    assert response.status_code == 403


async def test_admin_can_modify_other_users_record(
    client: AsyncClient, admin_user: dict, registered_user: dict
) -> None:
    created = await client.post(
        "/api/v1/records", headers=registered_user["headers"], json=RECORD_PAYLOAD
    )
    record_id = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/records/{record_id}", headers=admin_user["headers"], json={"value": 77.0}
    )
    assert patched.status_code == 200
    assert patched.json()["value"] == 77.0

    deleted = await client.delete(f"/api/v1/records/{record_id}", headers=admin_user["headers"])
    assert deleted.status_code == 200


async def test_user_cannot_read_another_users_profile(
    client: AsyncClient, admin_user: dict, registered_user: dict
) -> None:
    listing = await client.get(
        "/api/v1/users", headers=admin_user["headers"], params={"keyword": "root"}
    )
    admin_id = listing.json()["items"][0]["id"]

    response = await client.get(
        f"/api/v1/users/{admin_id}", headers=registered_user["headers"]
    )
    assert response.status_code == 403


async def test_public_registration_cannot_escalate_role(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "sneaky",
            "email": "sneaky@example.com",
            "password": "Sneaky@1234",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "user"


async def test_refresh_token_cannot_be_used_as_access_token(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"username": "dave", "email": "dave@example.com", "password": "Dave@1234"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"username": "dave", "password": "Dave@1234"}
    )
    refresh = login.json()["refresh_token"]

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401


async def test_refresh_rotates_and_revokes_old_token(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"username": "erin", "email": "erin@example.com", "password": "Erin@1234"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"username": "erin", "password": "Erin@1234"}
    )
    old_refresh = login.json()["refresh_token"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200
    new_access = rotated.json()["access_token"]
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    ).status_code == 200

    # 舊的 refresh token 已被撤銷，不可重複使用
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401

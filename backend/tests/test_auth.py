"""認證流程測試。"""

from __future__ import annotations

from httpx import AsyncClient


async def test_register_and_login(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "full_name": "Alice",
            "password": "Alice@1234",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "user"

    login = await client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "Alice@1234"}
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


async def test_login_with_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "bob@example.com", "password": "Bob@12345"},
    )
    response = await client.post(
        "/api/v1/auth/login", json={"username": "bob", "password": "WrongPass1"}
    )
    assert response.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_me_with_token(client: AsyncClient, registered_user: dict) -> None:
    response = await client.get("/api/v1/auth/me", headers=registered_user["headers"])
    assert response.status_code == 200
    assert response.json()["username"] == "tester"


async def test_duplicate_username_conflict(client: AsyncClient, registered_user: dict) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "tester",
            "email": "another@example.com",
            "password": "Tester@1234",
        },
    )
    assert response.status_code == 409

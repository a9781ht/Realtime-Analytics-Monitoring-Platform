"""測試共用設定：使用 SQLite（aiosqlite）取代 MariaDB，避免測試依賴外部服務。"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["SEED_DEMO_USERS"] = "false"
os.environ["GENERATOR_ENABLED"] = "false"
# 測試會在短時間內發出大量請求，放寬速率限制避免誤觸 429
os.environ["RATE_LIMIT_GENERAL"] = "100000"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture(scope="function", autouse=True)
async def prepare_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncClient:
    async def _override_get_db():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
async def make_user(client: AsyncClient):
    """直接以 ORM 建立指定角色的使用者並登入（公開註冊僅能建立 user 角色）。"""

    async def _make(username: str, role: UserRole, password: str = "Passw0rd@123") -> dict:
        async with TestSessionLocal() as session:
            session.add(
                User(
                    username=username,
                    email=f"{username}@example.com",
                    full_name=username,
                    hashed_password=hash_password(password),
                    role=role,
                    is_active=True,
                )
            )
            await session.commit()

        response = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"username": username, "headers": {"Authorization": f"Bearer {token}"}}

    return _make


@pytest.fixture
async def admin_user(make_user) -> dict:
    return await make_user("root", UserRole.ADMIN)


@pytest.fixture
async def viewer_user(make_user) -> dict:
    return await make_user("watcher", UserRole.VIEWER)


@pytest.fixture
async def registered_user(client: AsyncClient) -> dict:
    payload = {
        "username": "tester",
        "email": "tester@example.com",
        "full_name": "測試員",
        "password": "Tester@1234",
    }
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": payload["username"], "password": payload["password"]},
    )
    token = response.json()["access_token"]
    return {"payload": payload, "headers": {"Authorization": f"Bearer {token}"}}

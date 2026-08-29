"""資料庫初始化與示範種子資料。"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.enums import UserRole
from app.models.record import DataRecord
from app.models.user import User

logger = get_logger(__name__)

DEMO_USERS = [
    ("admin", "admin@example.com", "系統管理員", UserRole.ADMIN, "Admin@1234"),
    ("user", "user@example.com", "一般使用者", UserRole.USER, "User@1234"),
    ("viewer", "viewer@example.com", "唯讀使用者", UserRole.VIEWER, "Viewer@1234"),
]

DEMO_CATEGORIES = ["temperature", "humidity", "pressure", "vibration", "power"]


async def create_tables() -> None:
    """建立資料表（本機快速啟動用；正式環境請改用 Alembic migration）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("資料表檢查/建立完成")


async def seed_demo_data() -> None:
    """建立示範帳號與範例資料（僅在資料庫為空時執行）。"""
    if not settings.SEED_DEMO_USERS:
        return

    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        if existing:
            logger.info("已存在使用者資料，略過種子資料建立")
            return

        users: list[User] = []
        for username, email, full_name, role, password in DEMO_USERS:
            if username == "admin":
                username = settings.ADMIN_USERNAME
                email = settings.ADMIN_EMAIL
                password = settings.ADMIN_PASSWORD
            users.append(
                User(
                    username=username,
                    email=email,
                    full_name=full_name,
                    hashed_password=hash_password(password),
                    role=role,
                    is_active=True,
                )
            )
        session.add_all(users)
        await session.flush()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            DataRecord(
                title=f"{category} 監測值 #{index}",
                value=round(random.uniform(5, 100), 2),
                category=category,
                description="系統初始化產生的示範資料",
                recorded_at=now - timedelta(hours=index * 3),
                owner_id=users[index % 2].id,
            )
            for index, category in enumerate(DEMO_CATEGORIES * 8, start=1)
        ]
        session.add_all(records)
        await session.commit()

        logger.info("已建立 %d 個示範帳號與 %d 筆示範資料", len(users), len(records))

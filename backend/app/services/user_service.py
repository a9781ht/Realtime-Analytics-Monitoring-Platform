"""使用者相關業務邏輯（全部使用 SQLAlchemy ORM）。"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserAdminCreate, UserRegister, UserUpdate


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    payload: UserRegister | UserAdminCreate,
    *,
    role: UserRole = UserRole.USER,
) -> User:
    if await get_user_by_username(db, payload.username):
        raise ConflictError("使用者名稱已被註冊")
    if await get_user_by_email(db, str(payload.email)):
        raise ConflictError("Email 已被註冊")

    user = User(
        username=payload.username,
        email=str(payload.email),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=getattr(payload, "role", role),
        is_active=getattr(payload, "is_active", True),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    user = await get_user_by_username(db, username)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> tuple[list[User], int]:
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)

    conditions = []
    if keyword:
        pattern = f"%{keyword}%"
        conditions.append(
            or_(User.username.like(pattern), User.email.like(pattern), User.full_name.like(pattern))
        )
    if role is not None:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active == is_active)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(User.id.asc()).offset((page - 1) * size).limit(size)
    users = list((await db.execute(stmt)).unique().scalars().all())
    return users, total


async def update_user(db: AsyncSession, user: User, payload: UserUpdate) -> User:
    if payload.email and payload.email != user.email:
        existing = await get_user_by_email(db, str(payload.email))
        if existing and existing.id != user.id:
            raise ConflictError("Email 已被其他帳號使用")
        user.email = str(payload.email)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password:
        user.hashed_password = hash_password(payload.password)

    await db.commit()
    await db.refresh(user)
    return user


async def update_user_role(
    db: AsyncSession, user_id: int, role: UserRole, is_active: bool | None = None
) -> User:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("找不到指定使用者")
    user.role = role
    if is_active is not None:
        user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int) -> None:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("找不到指定使用者")
    await db.delete(user)
    await db.commit()

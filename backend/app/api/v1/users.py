"""使用者管理 API（含 Admin 權限操作）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, require_admin
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.user import UserAdminCreate, UserRead, UserRoleUpdate, UserUpdate
from app.services import log_service, user_service

router = APIRouter(prefix="/users", tags=["Users 使用者"])


@router.get("/me", response_model=UserRead, summary="取得自己的個人資料")
async def get_my_profile(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead, summary="更新自己的個人資料")
async def update_my_profile(
    payload: UserUpdate, db: DbSession, current_user: CurrentUser
) -> UserRead:
    user = await user_service.update_user(db, current_user, payload)
    return UserRead.model_validate(user)


@router.get(
    "",
    response_model=Page[UserRead],
    summary="查詢使用者列表（Admin）",
    dependencies=[Depends(require_admin)],
)
async def list_users(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> Page[UserRead]:
    users, total = await user_service.list_users(
        db, page=page, size=size, keyword=keyword, role=role, is_active=is_active
    )
    return Page.create([UserRead.model_validate(user) for user in users], total, page, size)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="建立使用者（Admin，可指定角色）",
)
async def create_user(
    payload: UserAdminCreate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
) -> UserRead:
    user = await user_service.create_user(db, payload)
    await log_service.write_log(
        level="INFO",
        action="user.create",
        message=f"{admin.username} 建立帳號 {user.username}（{user.role.value}）",
        user_id=admin.id,
    )
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead, summary="查詢單一使用者")
async def get_user(user_id: int, db: DbSession, current_user: CurrentUser) -> UserRead:
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise PermissionDeniedError("僅能查詢自己的帳號資訊")
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("找不到指定使用者")
    return UserRead.model_validate(user)


@router.patch("/{user_id}/role", response_model=UserRead, summary="調整使用者角色與狀態（Admin）")
async def update_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
) -> UserRead:
    if admin.id == user_id and payload.role != UserRole.ADMIN:
        raise PermissionDeniedError("不可將自己降權，請由其他管理員操作")
    user = await user_service.update_user_role(db, user_id, payload.role, payload.is_active)
    await log_service.write_log(
        level="INFO",
        action="user.update_role",
        message=f"{admin.username} 將 {user.username} 設為 {user.role.value}",
        user_id=admin.id,
    )
    return UserRead.model_validate(user)


@router.delete("/{user_id}", response_model=Message, summary="刪除使用者（Admin）")
async def delete_user(
    user_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
) -> Message:
    if admin.id == user_id:
        raise PermissionDeniedError("不可刪除自己的帳號")
    await user_service.delete_user(db, user_id)
    await log_service.write_log(
        level="WARNING",
        action="user.delete",
        message=f"{admin.username} 刪除使用者 id={user_id}",
        user_id=admin.id,
    )
    return Message(message="使用者已刪除")

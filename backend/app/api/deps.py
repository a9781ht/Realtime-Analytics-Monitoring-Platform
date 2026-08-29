"""FastAPI 依賴注入：目前使用者、角色權限、WebSocket 驗證。"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import jwt
from fastapi import Depends, Query, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.services.user_service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login/form")

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def _resolve_user(token: str, db: AsyncSession) -> User:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token 已過期，請重新登入") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("無效的認證憑證") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Token 類型錯誤，請使用 access token")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Token 缺少使用者資訊")

    user = await get_user_by_id(db, int(user_id))
    if user is None:
        raise AuthenticationError("使用者不存在")
    if not user.is_active:
        raise AuthenticationError("帳號已被停用")
    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    """由 Authorization: Bearer <token> 取得目前使用者。"""
    return await _resolve_user(token, db)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, User]]:
    """產生角色檢查依賴，例如 Depends(require_roles(UserRole.ADMIN))。"""

    async def _checker(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            allowed = ", ".join(role.value for role in roles)
            raise PermissionDeniedError(f"權限不足，此操作僅限：{allowed}")
        return current_user

    return _checker


# 常用權限組合
require_admin = require_roles(UserRole.ADMIN)
require_editor = require_roles(UserRole.ADMIN, UserRole.USER)


async def get_ws_user(
    websocket: WebSocket,
    db: DbSession,
    token: Annotated[str | None, Query(description="JWT access token")] = None,
) -> User | None:
    """WebSocket 認證：token 由 query string 傳入。"""
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="缺少 token")
        return None
    try:
        return await _resolve_user(token, db)
    except AuthenticationError as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=exc.message)
        return None

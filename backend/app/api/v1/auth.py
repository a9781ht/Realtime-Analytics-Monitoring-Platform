"""認證 API：註冊、登入、更新 Token、取得個人資訊。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_token, decode_token
from app.models.enums import UserRole
from app.schemas.common import Message
from app.schemas.token import LoginRequest, RefreshRequest, Token
from app.schemas.user import UserRead, UserRegister
from app.services import log_service, token_service, user_service

router = APIRouter(prefix="/auth", tags=["Auth 認證"])
logout_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login/form")


def _issue_token(user_id: int, role: str) -> Token:
    return Token(
        access_token=create_token(user_id, role, "access"),
        refresh_token=create_token(user_id, role, "refresh"),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="使用者註冊",
)
async def register(payload: UserRegister, db: DbSession) -> UserRead:
    """公開註冊，一律建立為 `user` 角色。"""
    user = await user_service.create_user(db, payload, role=UserRole.USER)
    await log_service.write_log(
        level="INFO", action="user.register", message=f"新使用者註冊：{user.username}",
        user_id=user.id,
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token, summary="使用者登入（JSON）")
async def login(payload: LoginRequest, db: DbSession) -> Token:
    user = await user_service.authenticate(db, payload.username, payload.password)
    if user is None:
        await log_service.write_log(
            level="WARNING", action="auth.login_failed", message=f"登入失敗：{payload.username}"
        )
        raise AuthenticationError("使用者名稱或密碼錯誤")
    if not user.is_active:
        raise AuthenticationError("帳號已被停用，請聯繫管理員")

    await log_service.write_log(
        level="INFO", action="auth.login", message=f"{user.username} 登入成功", user_id=user.id
    )
    return _issue_token(user.id, user.role.value)


@router.post(
    "/login/form",
    response_model=Token,
    summary="使用者登入（OAuth2 表單，供 Swagger Authorize 使用）",
)
async def login_form(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession
) -> Token:
    user = await user_service.authenticate(db, form_data.username, form_data.password)
    if user is None or not user.is_active:
        raise AuthenticationError("使用者名稱或密碼錯誤")
    return _issue_token(user.id, user.role.value)


@router.post("/refresh", response_model=Token, summary="以 Refresh Token 換發新 Token")
async def refresh_token(payload: RefreshRequest, db: DbSession) -> Token:
    try:
        data = decode_token(payload.refresh_token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Refresh Token 無效或已過期") from exc

    if data.get("type") != "refresh":
        raise AuthenticationError("Token 類型錯誤")

    jti = data.get("jti")
    exp = data.get("exp")
    if not isinstance(jti, str) or not isinstance(exp, (int, float)):
        raise AuthenticationError("Refresh Token 格式錯誤")
    if await token_service.is_revoked(db, jti):
        raise AuthenticationError("Refresh Token 已失效")
    await token_service.revoke(db, jti, datetime.fromtimestamp(exp, tz=timezone.utc))

    user = await user_service.get_user_by_id(db, int(data["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("使用者不存在或已停用")
    return _issue_token(user.id, user.role.value)


@router.get("/me", response_model=UserRead, summary="取得目前登入者資訊")
async def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/logout", response_model=Message, summary="登出")
async def logout(
    current_user: CurrentUser,
    db: DbSession,
    token: Annotated[str, Depends(logout_scheme)],
) -> Message:
    """撤銷目前 access token，並通知前端清除本機登入狀態。"""
    payload = decode_token(token)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if isinstance(jti, str) and isinstance(exp, (int, float)):
        await token_service.revoke(db, jti, datetime.fromtimestamp(exp, tz=timezone.utc))
    await log_service.write_log(
        level="INFO", action="auth.logout", message=f"{current_user.username} 登出",
        user_id=current_user.id,
    )
    return Message(message="已登出，請於前端清除 Token")

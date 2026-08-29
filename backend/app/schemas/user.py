"""使用者相關 Schema。"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole

_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128, examples=["User@1234"])

    @field_validator("password")
    @classmethod
    def _check_password_strength(cls, value: str) -> str:
        if not _PASSWORD_RE.match(value):
            raise ValueError("密碼長度需 8-128 碼，且至少包含英文字母與數字各一")
        return value


class UserRegister(UserCreate):
    """公開註冊：一律建立為 user 角色，避免權限提升。"""


class UserAdminCreate(UserCreate):
    role: UserRole = UserRole.USER
    is_active: bool = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _check_password_strength(cls, value: str | None) -> str | None:
        if value is not None and not _PASSWORD_RE.match(value):
            raise ValueError("密碼長度需 8-128 碼，且至少包含英文字母與數字各一")
        return value


class UserRoleUpdate(BaseModel):
    role: UserRole
    is_active: bool | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

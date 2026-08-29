"""認證相關 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access Token 有效秒數")


class TokenPayload(BaseModel):
    sub: str
    role: str
    type: str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, examples=["admin"])
    password: str = Field(..., min_length=6, max_length=128, examples=["Admin@1234"])


class RefreshRequest(BaseModel):
    refresh_token: str

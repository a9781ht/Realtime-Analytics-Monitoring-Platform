"""JWT 撤銷清單服務。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revoked_token import RevokedToken


async def is_revoked(db: AsyncSession, jti: str) -> bool:
    """檢查 Token 識別碼是否已撤銷。"""
    return (await db.execute(select(RevokedToken.id).where(RevokedToken.jti == jti))).scalar_one_or_none() is not None


async def revoke(db: AsyncSession, jti: str, expires_at: datetime) -> None:
    """將尚未過期的 Token 加入撤銷清單。"""
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    if expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        return
    if not await is_revoked(db, jti):
        db.add(RevokedToken(jti=jti, expires_at=expires_at))
        await db.commit()

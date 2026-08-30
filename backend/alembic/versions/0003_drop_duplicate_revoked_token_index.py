"""drop duplicate revoked token index

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29 16:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_revoked_tokens_jti"
TABLE_NAME = "revoked_tokens"


def upgrade() -> None:
    # 早期版本的 0002 會另外建立 ix_revoked_tokens_jti，與 jti 的 UniqueConstraint 重複。
    # 0002 已不再建立該索引，因此僅在既有資料庫上需要清除，全新資料庫則直接略過。
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(TABLE_NAME)
    if any(index["name"] == INDEX_NAME for index in indexes):
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)


def downgrade() -> None:
    # 該索引屬於重複結構，回退時不重建，避免全新資料庫產生 0002 未定義的索引。
    pass

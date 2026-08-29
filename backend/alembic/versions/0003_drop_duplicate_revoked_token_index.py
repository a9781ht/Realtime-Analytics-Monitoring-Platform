"""drop duplicate revoked token index

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29 16:00:00
"""
from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_revoked_tokens_jti", table_name="revoked_tokens")


def downgrade() -> None:
    op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"], unique=True)
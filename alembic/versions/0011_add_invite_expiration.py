"""add invite expiration

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invite_tokens", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_invite_tokens_expires_at", "invite_tokens", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invite_tokens_expires_at", table_name="invite_tokens")
    op.drop_column("invite_tokens", "expires_at")

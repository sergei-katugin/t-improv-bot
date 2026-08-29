"""add persistent FSM storage

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fsm_storage",
        sa.Column("bot_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("business_connection_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("destiny", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("state", sa.String(length=256), nullable=True),
        sa.Column("data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint(
            "bot_id", "chat_id", "user_id", "thread_id",
            "business_connection_id", "destiny",
        ),
    )


def downgrade() -> None:
    op.drop_table("fsm_storage")

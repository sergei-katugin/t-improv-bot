"""Add free_ad_channels table

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-25
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels = None
depends_on = None

_INITIAL_CHANNELS = ["@afishacy", "@iventycy", "@the_dudors"]


def upgrade() -> None:
    op.create_table(
        "free_ad_channels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.bulk_insert(
        sa.table(
            "free_ad_channels",
            sa.column("username", sa.String),
            sa.column("is_active", sa.Boolean),
        ),
        [{"username": u, "is_active": True} for u in _INITIAL_CHANNELS],
    )


def downgrade() -> None:
    op.drop_table("free_ad_channels")

"""add show waitlist

Revision ID: 0021
Revises: 0020
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attendee_name", sa.String(length=256), nullable=False),
        sa.Column("guests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("show_id", "user_id", name="uq_waitlist_show_user"),
    )
    op.create_index("ix_waitlist_show_pending", "waitlist_entries", ["show_id", "promoted_at", "cancelled_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_waitlist_show_pending", table_name="waitlist_entries")
    op.drop_table("waitlist_entries")

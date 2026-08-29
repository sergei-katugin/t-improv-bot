"""add indexes for hot-path queries

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_shows_active_date", "shows", ["is_active", "show_date"])
    op.create_index(
        "ix_registrations_user_active_show",
        "registrations",
        ["user_id", "is_cancelled", "show_id"],
    )
    op.create_index(
        "ix_registrations_show_active",
        "registrations",
        ["show_id", "is_cancelled"],
    )
    op.create_index(
        "ix_announcement_logs_show_sent",
        "announcement_logs",
        ["show_id", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_announcement_logs_show_sent", table_name="announcement_logs")
    op.drop_index("ix_registrations_show_active", table_name="registrations")
    op.drop_index("ix_registrations_user_active_show", table_name="registrations")
    op.drop_index("ix_shows_active_date", table_name="shows")

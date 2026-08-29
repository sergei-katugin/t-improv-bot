"""add analytics, check-in and feedback fields

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shows", sa.Column("checkin_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("shows", sa.Column("feedback_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("registrations", sa.Column("source", sa.String(length=64), nullable=True))
    op.add_column("registrations", sa.Column("checked_in_at", sa.DateTime(), nullable=True))
    op.add_column("registrations", sa.Column("feedback_requested_at", sa.DateTime(), nullable=True))
    op.add_column("manual_attendees", sa.Column("checked_in_at", sa.DateTime(), nullable=True))
    op.create_table(
        "show_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("show_id", "user_id", name="uq_show_feedback_show_user"),
    )
    op.create_index("ix_show_feedback_show", "show_feedback", ["show_id"])


def downgrade() -> None:
    op.drop_index("ix_show_feedback_show", table_name="show_feedback")
    op.drop_table("show_feedback")
    op.drop_column("registrations", "feedback_requested_at")
    op.drop_column("registrations", "checked_in_at")
    op.drop_column("registrations", "source")
    op.drop_column("shows", "feedback_enabled")
    op.drop_column("shows", "checkin_enabled")
    op.drop_column("manual_attendees", "checked_in_at")

"""add external attendee contacts and scoped check-in staff access

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("manual_attendees", sa.Column("contact", sa.String(length=512), nullable=True))
    op.create_table(
        "show_checkin_staff",
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("show_id", "user_id"),
    )
    op.create_table(
        "checkin_invite_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["used_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_checkin_invite_tokens_token", "checkin_invite_tokens", ["token"], unique=True)
    op.create_index("ix_checkin_invite_tokens_expires_at", "checkin_invite_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_checkin_invite_tokens_expires_at", table_name="checkin_invite_tokens")
    op.drop_index("ix_checkin_invite_tokens_token", table_name="checkin_invite_tokens")
    op.drop_table("checkin_invite_tokens")
    op.drop_table("show_checkin_staff")
    op.drop_column("manual_attendees", "contact")

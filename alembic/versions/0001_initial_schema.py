"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-06-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("role", sa.Enum("admin", "viewer", "user", name="userrole"), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "shows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("team_name", sa.String(256), nullable=False),
        sa.Column("show_date", sa.DateTime(), nullable=False, index=True),
        sa.Column("location", sa.String(512), nullable=False),
        sa.Column("location_url", sa.String(512), nullable=True),
        sa.Column("city", sa.String(128), nullable=False, index=True),
        sa.Column("poster_text", sa.Text(), nullable=True),
        sa.Column("poster_file_id", sa.String(256), nullable=True),
        sa.Column("pub_poster_file_id", sa.String(256), nullable=True),
        sa.Column("max_seats", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sheet_tab_name", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("attendee_name", sa.String(256), nullable=False),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("registered_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("remind_14d", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("remind_7d", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("remind_1d", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("reminded_14d", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("reminded_7d", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("reminded_1d", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("guests", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("show_id", "user_id", name="uq_registration_show_user"),
    )
    op.create_table(
        "manual_attendees",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "invite_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("role", sa.Enum("admin", "viewer", "user", name="userrole"), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "announcement_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer(), sa.ForeignKey("shows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("announcement_type", sa.String(32), nullable=False),
        sa.Column("channel_message_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("show_id", "announcement_type", name="uq_announcement_show_type"),
    )


def downgrade() -> None:
    op.drop_table("announcement_logs")
    op.drop_table("invite_tokens")
    op.drop_table("manual_attendees")
    op.drop_table("registrations")
    op.drop_table("shows")
    op.drop_table("users")

"""add per-show registration chat

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shows", sa.Column("registration_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("shows", sa.Column("registration_chat_title", sa.String(length=256), nullable=True))
    op.add_column("shows", sa.Column("registration_chat_name_mode", sa.String(length=16), nullable=False, server_default="short"))
    op.add_column("shows", sa.Column("checkin_mode", sa.String(length=16), nullable=False, server_default="named"))
    op.add_column("shows", sa.Column("checkin_counter", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("shows", sa.Column("checkin_milestone", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("manual_attendees", sa.Column("source", sa.String(length=64), nullable=True))
    op.add_column("manual_attendees", sa.Column("organizer_reminded_at", sa.DateTime(), nullable=True))
    op.add_column("manual_attendees", sa.Column("notification_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("manual_attendees", sa.Column("checked_in_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("registrations", sa.Column("checked_in_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("registrations", "checked_in_count")
    op.drop_column("manual_attendees", "checked_in_count")
    op.drop_column("manual_attendees", "notification_confirmed_at")
    op.drop_column("manual_attendees", "organizer_reminded_at")
    op.drop_column("manual_attendees", "source")
    op.drop_column("shows", "registration_chat_name_mode")
    op.drop_column("shows", "checkin_milestone")
    op.drop_column("shows", "checkin_counter")
    op.drop_column("shows", "checkin_mode")
    op.drop_column("shows", "registration_chat_title")
    op.drop_column("shows", "registration_chat_id")

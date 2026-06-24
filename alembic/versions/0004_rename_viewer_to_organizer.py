"""rename viewer role to organizer

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role='organizer' WHERE role='viewer'")
    op.execute("UPDATE invite_tokens SET role='organizer' WHERE role='viewer'")


def downgrade() -> None:
    op.execute("UPDATE users SET role='viewer' WHERE role='organizer'")
    op.execute("UPDATE invite_tokens SET role='viewer' WHERE role='organizer'")

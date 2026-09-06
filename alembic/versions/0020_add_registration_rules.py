"""add per-show registration rules

Revision ID: 0020
Revises: 0019
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.add_column(sa.Column("max_guests", sa.Integer(), nullable=False, server_default="2"))
        batch_op.add_column(sa.Column("registration_closes_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.drop_column("registration_closes_at")
        batch_op.drop_column("max_guests")

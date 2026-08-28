"""Add confirmed to registrations, drop remind_0d

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-25
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("registrations") as batch_op:
        batch_op.add_column(sa.Column("confirmed", sa.Boolean(), nullable=True))
        batch_op.drop_column("remind_0d")


def downgrade() -> None:
    with op.batch_alter_table("registrations") as batch_op:
        batch_op.add_column(sa.Column("remind_0d", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.drop_column("confirmed")

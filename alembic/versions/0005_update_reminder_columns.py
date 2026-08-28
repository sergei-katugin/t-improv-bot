"""Update reminder columns: replace 14d with 2d, add 0d (day-of)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-25
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("registrations") as batch_op:
        batch_op.add_column(sa.Column("remind_2d", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("remind_0d", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("reminded_2d", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("reminded_0d", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.drop_column("remind_14d")
        batch_op.drop_column("reminded_14d")


def downgrade() -> None:
    with op.batch_alter_table("registrations") as batch_op:
        batch_op.add_column(sa.Column("remind_14d", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("reminded_14d", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.drop_column("remind_2d")
        batch_op.drop_column("remind_0d")
        batch_op.drop_column("reminded_2d")
        batch_op.drop_column("reminded_0d")

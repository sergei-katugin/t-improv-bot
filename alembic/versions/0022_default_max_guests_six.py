"""default maximum guests to six

Revision ID: 0022
Revises: 0021
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.alter_column("max_guests", existing_type=sa.Integer(), server_default="6", existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.alter_column("max_guests", existing_type=sa.Integer(), server_default="2", existing_nullable=False)

"""track registration chat summaries

Revision ID: 0023
Revises: 0022
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.add_column(sa.Column("registration_chat_summary_sent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.drop_column("registration_chat_summary_sent_at")

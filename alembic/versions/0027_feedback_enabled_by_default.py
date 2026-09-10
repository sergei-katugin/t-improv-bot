"""Enable feedback by default for new shows.

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.alter_column(
            "feedback_enabled", existing_type=sa.Boolean(),
            nullable=False, server_default=sa.true(),
        )


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch_op:
        batch_op.alter_column(
            "feedback_enabled", existing_type=sa.Boolean(),
            nullable=False, server_default=sa.false(),
        )

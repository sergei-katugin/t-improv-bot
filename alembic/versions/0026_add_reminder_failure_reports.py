"""Track personal reminder failures reported to organizers.

Revision ID: 0026
Revises: 0025
"""

from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


_COLUMNS = (
    "reminder_failure_reported_7d",
    "reminder_failure_reported_2d",
    "reminder_failure_reported_1d",
    "reminder_failure_reported_0d",
)


def upgrade() -> None:
    with op.batch_alter_table("registrations") as batch_op:
        for name in _COLUMNS:
            batch_op.add_column(
                sa.Column(name, sa.Boolean(), server_default=sa.false(), nullable=False)
            )


def downgrade() -> None:
    with op.batch_alter_table("registrations") as batch_op:
        for name in reversed(_COLUMNS):
            batch_op.drop_column(name)

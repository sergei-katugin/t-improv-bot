"""Add a second announcement text for newcomers.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.add_column(sa.Column("poster_text_newcomer", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.drop_column("poster_text_newcomer")

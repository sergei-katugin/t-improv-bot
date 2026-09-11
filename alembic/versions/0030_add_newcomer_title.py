"""Add an optional announcement title for newcomers.

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.add_column(sa.Column("title_newcomer", sa.String(length=256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shows") as batch:
        batch.drop_column("title_newcomer")

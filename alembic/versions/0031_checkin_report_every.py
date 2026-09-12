"""Configure arrival report frequency.

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shows", sa.Column("checkin_report_every", sa.Integer(), nullable=False, server_default="10"))


def downgrade():
    with op.batch_alter_table("shows") as batch:
        batch.drop_column("checkin_report_every")

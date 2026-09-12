"""Enable entry tracking for all existing and new shows."""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("UPDATE shows SET checkin_enabled = true"))
    with op.batch_alter_table("shows") as batch:
        batch.alter_column("checkin_enabled", existing_type=sa.Boolean(), server_default=sa.true(), existing_nullable=False)


def downgrade():
    # Previous per-show choices cannot be recovered; keep recorded attendance.
    with op.batch_alter_table("shows") as batch:
        batch.alter_column("checkin_enabled", existing_type=sa.Boolean(), server_default=sa.false(), existing_nullable=False)

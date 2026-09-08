"""Add indexes for common owner and attendee lookups.

Revision ID: 0025
Revises: 0024
"""

from alembic import op


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_shows_creator_date", "shows", ["creator_id", "show_date"])
    op.create_index("ix_manual_attendees_show", "manual_attendees", ["show_id"])
    op.create_index("ix_teams_creator_active", "teams", ["creator_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_teams_creator_active", table_name="teams")
    op.drop_index("ix_manual_attendees_show", table_name="manual_attendees")
    op.drop_index("ix_shows_creator_date", table_name="shows")

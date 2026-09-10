"""Set registration closing five minutes before every show.

Revision ID: 0028
Revises: 0027
"""

from datetime import timedelta

from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    shows = sa.table(
        "shows",
        sa.column("id", sa.Integer()),
        sa.column("show_date", sa.DateTime()),
        sa.column("registration_closes_at", sa.DateTime()),
    )
    connection = op.get_bind()
    for show_id, show_date in connection.execute(
        sa.select(shows.c.id, shows.c.show_date)
    ):
        connection.execute(
            shows.update().where(shows.c.id == show_id).values(
                registration_closes_at=show_date - timedelta(minutes=5)
            )
        )


def downgrade() -> None:
    # The previous custom values cannot be reconstructed.
    pass

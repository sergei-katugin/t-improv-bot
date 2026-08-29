"""normalize existing local show dates to UTC

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-29
"""
from datetime import timezone
from typing import Sequence, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOCAL_TZ = ZoneInfo("Europe/Nicosia")


def _convert(to_utc: bool) -> None:
    connection = op.get_bind()
    shows = sa.table("shows", sa.column("id", sa.Integer), sa.column("show_date", sa.DateTime))
    for show_id, show_date in connection.execute(sa.select(shows.c.id, shows.c.show_date)):
        if show_date is None:
            continue
        if to_utc:
            converted = show_date.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        else:
            converted = show_date.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).replace(tzinfo=None)
        connection.execute(
            shows.update().where(shows.c.id == show_id).values(show_date=converted)
        )


def upgrade() -> None:
    _convert(to_utc=True)


def downgrade() -> None:
    _convert(to_utc=False)

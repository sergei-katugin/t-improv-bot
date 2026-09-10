"""Hash stored organizer and check-in invite tokens.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from alembic import op


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def upgrade() -> None:
    connection = op.get_bind()
    for table_name in ("invite_tokens", "checkin_invite_tokens"):
        table = sa.table(table_name, sa.column("id", sa.Integer), sa.column("token", sa.String(64)))
        rows = connection.execute(sa.select(table.c.id, table.c.token)).all()
        for row_id, token in rows:
            connection.execute(
                table.update().where(table.c.id == row_id).values(token=_digest(token)),
            )


def downgrade() -> None:
    # Hashing is intentionally irreversible; the schema itself is unchanged.
    pass

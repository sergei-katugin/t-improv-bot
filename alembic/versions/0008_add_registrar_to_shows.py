"""add registrar to shows

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('shows', sa.Column('registrar_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_shows_registrar_users', 'shows', 'users', ['registrar_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_shows_registrar_users', 'shows', type_='foreignkey')
    op.drop_column('shows', 'registrar_id')

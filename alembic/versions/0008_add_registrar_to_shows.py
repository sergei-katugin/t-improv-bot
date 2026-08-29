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
    with op.batch_alter_table('shows') as batch_op:
        batch_op.add_column(sa.Column('registrar_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_shows_registrar_users', 'users', ['registrar_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('shows') as batch_op:
        batch_op.drop_constraint('fk_shows_registrar_users', type_='foreignkey')
        batch_op.drop_column('registrar_id')

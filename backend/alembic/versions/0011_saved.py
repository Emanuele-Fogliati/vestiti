"""saved: trips.saved (only the trips the traveller pressed Save on show in Saved trips) and
users.saved_trails (the walks they saved). Trips made before this stay saved.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-16 09:45:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('trips') as b:
        b.add_column(sa.Column('saved', sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table('trips') as b:
        b.alter_column('saved', server_default=sa.false())
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('saved_trails', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('users') as b:
        b.drop_column('saved_trails')
    with op.batch_alter_table('trips') as b:
        b.drop_column('saved')

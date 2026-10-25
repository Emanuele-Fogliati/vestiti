"""visited places per stop, estimated dates

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 17:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stops') as b:
        b.add_column(sa.Column('visits', sa.JSON(), nullable=False, server_default='[]'))
        b.add_column(sa.Column('days_estimated', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('trips') as b:
        b.add_column(sa.Column('start_estimated', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('trips') as b:
        b.drop_column('start_estimated')
    with op.batch_alter_table('stops') as b:
        b.drop_column('days_estimated')
        b.drop_column('visits')

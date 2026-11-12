"""trip board: stop status, where you sleep, how you get there, day plan; home airport

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12 21:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stops') as b:
        b.add_column(sa.Column('status', sa.String(8), nullable=False, server_default='flex'))
        b.add_column(sa.Column('fixed_note', sa.String(120)))
        b.add_column(sa.Column('sleep', sa.String(200)))
        b.add_column(sa.Column('arrival', sa.JSON()))
        b.add_column(sa.Column('plan', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('trips') as b:
        b.add_column(sa.Column('home_airport', sa.String(3)))
        b.add_column(sa.Column('return_leg', sa.JSON()))


def downgrade():
    with op.batch_alter_table('trips') as b:
        b.drop_column('return_leg')
        b.drop_column('home_airport')
    with op.batch_alter_table('stops') as b:
        b.drop_column('plan')
        b.drop_column('arrival')
        b.drop_column('sleep')
        b.drop_column('fixed_note')
        b.drop_column('status')

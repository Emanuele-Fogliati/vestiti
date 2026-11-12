"""users.preferred_brands: brands the traveller prefers in the kit

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-12 23:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('preferred_brands', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('users') as b:
        b.drop_column('preferred_brands')

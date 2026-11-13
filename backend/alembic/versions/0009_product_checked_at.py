"""products.checked_at: when price and stock were last read from the shop

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-13 11:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products') as b:
        b.add_column(sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('products') as b:
        b.drop_column('checked_at')

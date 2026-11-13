"""markets: products.market (us | eu) and users.market (where the traveller shops)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-13 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products') as b:
        b.add_column(sa.Column('market', sa.String(2), nullable=False, server_default='eu'))
        b.create_index('ix_products_market', ['market'])
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('market', sa.String(2), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as b:
        b.drop_column('market')
    with op.batch_alter_table('products') as b:
        b.drop_index('ix_products_market')
        b.drop_column('market')

"""wardrobe items remember the model they were matched to (by name or photos)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26 13:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('wardrobe_items') as b:
        # lib:<known model id> or product:<product id>; empty when typed by hand or estimated
        b.add_column(sa.Column('model_ref', sa.String(120), nullable=True))
        # hand | search | photo
        b.add_column(sa.Column('added_via', sa.String(10), nullable=True))
        # extra data of the matched model (fill power, waterproof rating)
        b.add_column(sa.Column('specs', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('wardrobe_items') as b:
        b.drop_column('specs')
        b.drop_column('added_via')
        b.drop_column('model_ref')

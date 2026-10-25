"""traveller profile: pace, evenings, quiz done

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 16:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('pace', sa.String(length=10), nullable=False,
                                     server_default='average'))
    op.add_column('users', sa.Column('evenings', sa.String(length=10), nullable=False,
                                     server_default='sometimes'))
    op.add_column('users', sa.Column('profile_done_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('users', 'profile_done_at')
    op.drop_column('users', 'evenings')
    op.drop_column('users', 'pace')

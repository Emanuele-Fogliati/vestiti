"""accounts: session version, email links; trips remember their recommended itinerary

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))
    with op.batch_alter_table('trips') as b:
        b.add_column(sa.Column('source_itinerary', sa.String(80), nullable=True))
    op.create_table(
        'auth_tokens',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('purpose', sa.String(10), nullable=False),
        sa.Column('email', sa.String(320), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_auth_tokens_token_hash', 'auth_tokens', ['token_hash'], unique=True)
    op.create_index('ix_auth_tokens_email', 'auth_tokens', ['email'])
    op.create_index('ix_auth_tokens_user_id', 'auth_tokens', ['user_id'])


def downgrade():
    op.drop_index('ix_auth_tokens_user_id', 'auth_tokens')
    op.drop_index('ix_auth_tokens_email', 'auth_tokens')
    op.drop_index('ix_auth_tokens_token_hash', 'auth_tokens')
    op.drop_table('auth_tokens')
    with op.batch_alter_table('trips') as b:
        b.drop_column('source_itinerary')
    with op.batch_alter_table('users') as b:
        b.drop_column('session_version')

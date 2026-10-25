"""verified place registry, place checks on stops, trip countries

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'places',
        sa.Column('id', sa.String(80), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('country_code', sa.String(2), nullable=False),
        sa.Column('admin', sa.String(200)),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('elevation_m', sa.Float(), nullable=False),
        sa.Column('base', sa.String(80)),
        sa.Column('aliases', sa.JSON(), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('verified_on', sa.Date()),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('problems', sa.JSON(), nullable=False),
    )
    op.create_index('ix_places_country_code', 'places', ['country_code'])
    with op.batch_alter_table('stops') as b:
        b.add_column(sa.Column('place_status', sa.String(10)))
        b.add_column(sa.Column('place_note', sa.Text()))
    with op.batch_alter_table('trips') as b:
        b.add_column(sa.Column('countries', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    with op.batch_alter_table('trips') as b:
        b.drop_column('countries')
    with op.batch_alter_table('stops') as b:
        b.drop_column('place_note')
        b.drop_column('place_status')
    op.drop_index('ix_places_country_code', 'places')
    op.drop_table('places')

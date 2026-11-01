"""Add the offline-synced knowledge paper pool for the home feed."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '018_discovery_pool'
down_revision: Union[str, Sequence[str], None] = '017_conference_follows'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'discovery_pool_papers',
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('abstract', sa.Text(), nullable=False),
        sa.Column('authors', postgresql.JSONB(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('venue', sa.Text(), nullable=False),
        sa.Column('image_id', sa.Text(), nullable=False),
        sa.Column('subjects', postgresql.JSONB(), nullable=False),
        sa.Column('keywords', postgresql.JSONB(), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('paper_id', name='pk_discovery_pool_papers'),
    )
    op.create_index('idx_discovery_pool_papers_year_synced', 'discovery_pool_papers', ['year', 'synced_at'])


def downgrade() -> None:
    op.drop_index('idx_discovery_pool_papers_year_synced', table_name='discovery_pool_papers')
    op.drop_table('discovery_pool_papers')

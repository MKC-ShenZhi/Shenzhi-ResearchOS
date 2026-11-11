"""Store structured paper topics in the home discovery pool."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '024_discovery_pool_topics'
down_revision = '023_merge_conference_chat'
branch_labels = depends_on = None


def upgrade() -> None:
    op.add_column(
        'discovery_pool_papers',
        sa.Column('topics', JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('discovery_pool_papers', 'topics')

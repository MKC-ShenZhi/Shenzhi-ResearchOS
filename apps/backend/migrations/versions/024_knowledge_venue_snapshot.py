"""Persist the last verified knowledge conference directory."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '024_knowledge_venue_snapshot'
down_revision = '023_merge_conference_chat'
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        'knowledge_conference_snapshot',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('items', JSONB(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('id = 1', name='knowledge_conference_snapshot_singleton'),
    )


def downgrade():
    op.drop_table('knowledge_conference_snapshot')

"""Add user behavior facts and rebuildable recommendation profiles."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '015_recommendation_foundation'
down_revision = '014_platform_snapshots'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'behavior_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('entity_type', sa.Text(), nullable=False),
        sa.Column('entity_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('request_id', sa.Text()),
        sa.Column('query_id', postgresql.UUID(as_uuid=True)),
        sa.Column('rank', sa.Integer()),
        sa.Column('duration_seconds', sa.Integer()),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_behavior_events_user_time', 'behavior_events', ['user_id', sa.text('received_at DESC')])
    op.create_index('idx_behavior_events_user_entity', 'behavior_events', ['user_id', 'entity_type', 'entity_id'])
    op.create_index('idx_behavior_events_received', 'behavior_events', ['received_at'])
    op.create_table(
        'user_interest_profiles',
        sa.Column('user_id', sa.Text(), primary_key=True),
        sa.Column('algorithm_version', sa.Text(), nullable=False),
        sa.Column('profile_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_event_at', sa.DateTime(timezone=True)),
        sa.Column('profile_data', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        'recommendation_snapshots',
        sa.Column('request_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('algorithm_version', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('items', postgresql.JSONB(), nullable=False),
    )
    op.create_index('idx_recommendation_snapshots_user_expiry', 'recommendation_snapshots', ['user_id', 'expires_at'])
    op.create_index('idx_recommendation_snapshots_expiry', 'recommendation_snapshots', ['expires_at'])


def downgrade() -> None:
    op.drop_index('idx_recommendation_snapshots_expiry', table_name='recommendation_snapshots')
    op.drop_index('idx_recommendation_snapshots_user_expiry', table_name='recommendation_snapshots')
    op.drop_table('recommendation_snapshots')
    op.drop_table('user_interest_profiles')
    op.drop_index('idx_behavior_events_received', table_name='behavior_events')
    op.drop_index('idx_behavior_events_user_entity', table_name='behavior_events')
    op.drop_index('idx_behavior_events_user_time', table_name='behavior_events')
    op.drop_table('behavior_events')

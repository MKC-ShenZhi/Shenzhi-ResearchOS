"""Add the daily platform statistics snapshot published for the knowledge base."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '014_platform_snapshots'
down_revision: Union[str, Sequence[str], None] = '013_paper_likes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'stats_snapshot_runs',
        sa.Column('snapshot_date', sa.Date(), primary_key=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('snapshot_version', sa.Text(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.CheckConstraint("status in ('completed', 'failed')", name='ck_stats_snapshot_runs_status'),
    )
    op.create_table(
        'paper_stats_daily',
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('collector_count', sa.Integer(), nullable=False),
        sa.Column('like_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('snapshot_date', 'paper_id', name='pk_paper_stats_daily'),
        sa.ForeignKeyConstraint(
            ['snapshot_date'], ['stats_snapshot_runs.snapshot_date'],
            name='fk_paper_stats_daily_snapshot_date', ondelete='CASCADE',
        ),
        sa.CheckConstraint('collector_count >= 0', name='ck_paper_stats_daily_collector_count'),
        sa.CheckConstraint('like_count >= 0', name='ck_paper_stats_daily_like_count'),
    )
    op.create_table(
        'topic_stats_daily',
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('topic_id', sa.Text(), nullable=False),
        sa.Column('follower_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('snapshot_date', 'topic_id', name='pk_topic_stats_daily'),
        sa.ForeignKeyConstraint(
            ['snapshot_date'], ['stats_snapshot_runs.snapshot_date'],
            name='fk_topic_stats_daily_snapshot_date', ondelete='CASCADE',
        ),
        sa.CheckConstraint('follower_count >= 0', name='ck_topic_stats_daily_follower_count'),
    )


def downgrade() -> None:
    op.drop_table('topic_stats_daily')
    op.drop_table('paper_stats_daily')
    op.drop_table('stats_snapshot_runs')

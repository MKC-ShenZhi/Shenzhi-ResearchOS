"""Persist home scheduler intervals across workers and restarts."""

import sqlalchemy as sa
from alembic import op

revision = '026_home_scheduler_state'
down_revision = '025_merge_background_jobs'
branch_labels = depends_on = None


def upgrade() -> None:
    op.create_table(
        'home_scheduler_state',
        sa.Column('job', sa.Text(), primary_key=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('home_scheduler_state')

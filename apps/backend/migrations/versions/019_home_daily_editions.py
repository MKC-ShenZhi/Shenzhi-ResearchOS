"""Rename the retired recommendation candidate table to the home daily edition table.

Rows from the retired feature stay in place; the feed already treats their
payloads as missing editions, and the scheduler's purge drops them over time.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '019_home_daily_editions'
down_revision: Union[str, Sequence[str], None] = '018_discovery_pool'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table('daily_recommendations', 'home_daily_editions')
    op.alter_column('home_daily_editions', 'recommendation_date', new_column_name='edition_date')
    op.execute('ALTER INDEX daily_recommendations_pkey RENAME TO home_daily_editions_pkey')


def downgrade() -> None:
    op.execute('ALTER INDEX home_daily_editions_pkey RENAME TO daily_recommendations_pkey')
    op.alter_column('home_daily_editions', 'edition_date', new_column_name='recommendation_date')
    op.rename_table('home_daily_editions', 'daily_recommendations')

"""Let a recommendation snapshot start with the shared first page and gain the personal feed later."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '020_snapshot_complete'
down_revision: Union[str, Sequence[str], None] = '019_home_daily_editions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('recommendation_snapshots', sa.Column(
        'complete', sa.Boolean(), nullable=False, server_default=sa.text('true'),
    ))


def downgrade() -> None:
    op.drop_column('recommendation_snapshots', 'complete')

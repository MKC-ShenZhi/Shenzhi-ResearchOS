"""Track completed PDF reads separately from visits."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '009_paper_read_completion'
down_revision: Union[str, Sequence[str], None] = '008_daily_recommendations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reading_history', sa.Column('read_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('reading_history', 'read_at')

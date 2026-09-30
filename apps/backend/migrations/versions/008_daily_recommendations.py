"""Add one JSONB recommendation candidate pool per day."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '008_daily_recommendations'
down_revision: Union[str, Sequence[str], None] = '007_agent_sessions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'daily_recommendations',
        sa.Column('recommendation_date', sa.Date(), primary_key=True),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('daily_recommendations')

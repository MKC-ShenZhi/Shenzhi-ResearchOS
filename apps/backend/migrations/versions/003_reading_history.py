"""Add authenticated paper reading history."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '003_reading_history'
down_revision: Union[str, Sequence[str], None] = '002_anon_expiry_idx'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'reading_history',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('last_viewed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('user_id', 'paper_id', name='uq_reading_history_user_paper'),
    )
    op.create_index(
        'idx_reading_history_user_viewed',
        'reading_history',
        ['user_id', sa.text('last_viewed_at DESC')],
    )


def downgrade() -> None:
    op.drop_index('idx_reading_history_user_viewed', table_name='reading_history')
    op.drop_table('reading_history')
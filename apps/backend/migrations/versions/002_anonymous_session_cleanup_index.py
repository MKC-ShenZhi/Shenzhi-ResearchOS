"""Add an index for expired anonymous Chat session cleanup."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002_anon_expiry_idx'
down_revision: Union[str, Sequence[str], None] = '001_chat_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'idx_chat_sessions_anonymous_expiry',
        'chat_sessions',
        ['updated_at'],
        postgresql_where=sa.text("owner LIKE 'anon:%'"),
    )


def downgrade() -> None:
    op.drop_index('idx_chat_sessions_anonymous_expiry', table_name='chat_sessions')

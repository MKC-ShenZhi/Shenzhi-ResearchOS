"""Add account-level topic follows."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '012_topic_follows'
down_revision: Union[str, Sequence[str], None] = '011_agent_uploads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'topic_follows',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('topic_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('user_id', 'topic_id', name='pk_topic_follows'),
    )
    op.create_index('idx_topic_follows_topic', 'topic_follows', ['topic_id'])
    op.create_index('idx_topic_follows_user_created', 'topic_follows', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_topic_follows_user_created', table_name='topic_follows')
    op.drop_index('idx_topic_follows_topic', table_name='topic_follows')
    op.drop_table('topic_follows')

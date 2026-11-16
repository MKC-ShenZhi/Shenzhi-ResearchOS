"""Add account-level paper likes."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '013_paper_likes'
down_revision: Union[str, Sequence[str], None] = '012_topic_follows'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'paper_likes',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('user_id', 'paper_id', name='pk_paper_likes'),
    )
    op.create_index('idx_paper_likes_paper', 'paper_likes', ['paper_id'])
    op.create_index('idx_paper_likes_user_created', 'paper_likes', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_paper_likes_user_created', table_name='paper_likes')
    op.drop_index('idx_paper_likes_paper', table_name='paper_likes')
    op.drop_table('paper_likes')

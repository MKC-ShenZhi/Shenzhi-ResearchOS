"""Add account-level conference deadline follows."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '017_conference_follows'
down_revision: Union[str, Sequence[str], None] = '016_request_idempotency'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conference_follows',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('conference_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('user_id', 'conference_id', name='pk_conference_follows'),
    )
    op.create_index('idx_conference_follows_user_created', 'conference_follows', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_conference_follows_user_created', table_name='conference_follows')
    op.drop_table('conference_follows')

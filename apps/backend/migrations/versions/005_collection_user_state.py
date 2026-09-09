"""Prevent deleted default collection folders from being recreated."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '005_collection_user_state'
down_revision: Union[str, Sequence[str], None] = '004_collections'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'collection_user_states',
        sa.Column('user_id', sa.Text(), primary_key=True),
        sa.Column('initialized_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    # Users with existing folders have already passed initialization. New users
    # are marked on their first collection request by the service.
    op.execute(
        sa.text(
            "INSERT INTO collection_user_states (user_id) "
            "SELECT DISTINCT user_id FROM collection_folders"
        )
    )


def downgrade() -> None:
    op.drop_table('collection_user_states')
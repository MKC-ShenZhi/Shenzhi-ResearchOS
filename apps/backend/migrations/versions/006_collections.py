"""Add user collection folders, memberships and initialization state."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '006_collections'
down_revision: Union[str, Sequence[str], None] = '005_reading_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'collection_folders',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('user_id', 'name', name='uq_collection_folders_user_name'),
    )
    op.create_index('idx_collection_folders_user_created', 'collection_folders', ['user_id', 'created_at', 'id'])
    op.create_table(
        'collection_items',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('folder_id', sa.Integer(), sa.ForeignKey('collection_folders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('paper_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('folder_id', 'paper_id', name='uq_collection_items_folder_paper'),
    )
    op.create_index('idx_collection_items_paper', 'collection_items', ['paper_id'])
    op.create_index('idx_collection_items_folder_created', 'collection_items', ['folder_id', 'created_at'])
    op.create_table(
        'collection_user_states',
        sa.Column('user_id', sa.Text(), primary_key=True),
        sa.Column('initialized_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    # Backfill for databases that already hold folders (for example a partially
    # migrated environment): those users have passed initialization. New users
    # are marked on their first collection request by the service.
    op.execute(
        sa.text(
            "INSERT INTO collection_user_states (user_id) "
            "SELECT DISTINCT user_id FROM collection_folders"
        )
    )


def downgrade() -> None:
    # Drop dependent tables before the folders they reference.
    op.drop_table('collection_user_states')
    op.drop_index('idx_collection_items_folder_created', table_name='collection_items')
    op.drop_index('idx_collection_items_paper', table_name='collection_items')
    op.drop_table('collection_items')
    op.drop_index('idx_collection_folders_user_created', table_name='collection_folders')
    op.drop_table('collection_folders')
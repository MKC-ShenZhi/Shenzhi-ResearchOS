"""Store user-owned PDFs in personal library folders."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '010_private_papers'
down_revision: Union[str, Sequence[str], None] = '009_paper_read_completion'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_papers',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('folder_id', sa.Integer(), sa.ForeignKey('collection_folders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_private_papers_user_folder_created', 'private_papers', ['user_id', 'folder_id', sa.text('created_at DESC')])


def downgrade() -> None:
    op.drop_index('idx_private_papers_user_folder_created', table_name='private_papers')
    op.drop_table('private_papers')

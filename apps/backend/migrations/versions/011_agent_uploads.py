"""Short-lived parsed Agent uploads shared across backend instances."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '011_agent_uploads'
down_revision: Union[str, Sequence[str], None] = '010_private_papers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_uploads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('owner', sa.Text(), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('original_length', sa.Integer(), nullable=False),
        sa.Column('final_length', sa.Integer(), nullable=False),
        sa.Column('truncated', sa.Boolean(), nullable=False),
        sa.Column('warning', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_agent_uploads_owner_expires', 'agent_uploads', ['owner', 'expires_at'])
    op.create_index('idx_agent_uploads_expires', 'agent_uploads', ['expires_at'])


def downgrade() -> None:
    op.drop_index('idx_agent_uploads_expires', table_name='agent_uploads')
    op.drop_index('idx_agent_uploads_owner_expires', table_name='agent_uploads')
    op.drop_table('agent_uploads')

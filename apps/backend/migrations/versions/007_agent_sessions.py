"""Add persistent Agent sessions and completed run turns."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '007_agent_sessions'
down_revision: Union[str, Sequence[str], None] = '006_collections'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('owner', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('settings', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('branched_from', sa.Text(), nullable=True),
        sa.Column('import_key', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_agent_sessions_owner_updated', 'agent_sessions',
                    ['owner', sa.text('updated_at DESC'), sa.text('id DESC')])
    op.create_index('uq_agent_sessions_owner_import_key', 'agent_sessions', ['owner', 'import_key'],
                    unique=True, postgresql_where=sa.text('import_key IS NOT NULL'))
    op.create_table(
        'agent_turns',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('session_id', sa.Text(),
                  sa.ForeignKey('agent_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_content', sa.Text(), nullable=False),
        sa.Column('settings', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('assistant_content', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('reasoning', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('process', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('steers', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('report', sa.Text(), nullable=True),
        sa.Column('sources', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('question', postgresql.JSONB(), nullable=True),
        sa.Column('warnings', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('stopped', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('stop_reason', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('usage', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('transcript', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'stopped', 'failed', 'timeout', 'awaiting_input')",
            name='chk_agent_turns_status',
        ),
    )
    op.create_index('idx_agent_turns_session_created', 'agent_turns', ['session_id', 'created_at', 'id'])
    op.create_index('uq_agent_turns_active', 'agent_turns', ['session_id'], unique=True,
                    postgresql_where=sa.text("status = 'running'"))


def downgrade() -> None:
    op.drop_index('uq_agent_turns_active', table_name='agent_turns')
    op.drop_index('idx_agent_turns_session_created', table_name='agent_turns')
    op.drop_table('agent_turns')
    op.drop_index('uq_agent_sessions_owner_import_key', table_name='agent_sessions')
    op.drop_index('idx_agent_sessions_owner_updated', table_name='agent_sessions')
    op.drop_table('agent_sessions')

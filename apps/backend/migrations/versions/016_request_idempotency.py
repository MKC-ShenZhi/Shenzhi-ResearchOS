"""Persist idempotency keys and worker leases with Chat and Agent resources."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '016_request_idempotency'
# 015 is reserved for the parallel recommendation foundation, which also builds
# on 014 and touches disjoint tables. Whichever lands in dev second must restore
# a single head (see docs/engineering/idempotency-delivery.md) without editing a
# revision that a shared database has already applied.
down_revision: Union[str, Sequence[str], None] = '014_platform_snapshots'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chat_messages', sa.Column('idempotency_owner', sa.Text(), nullable=True))
    op.add_column('chat_messages', sa.Column('idempotency_scope', sa.Text(), nullable=True))
    op.add_column('chat_messages', sa.Column('idempotency_key', sa.Text(), nullable=True))
    op.add_column('chat_messages', sa.Column('idempotency_fingerprint', sa.Text(), nullable=True))
    op.add_column('chat_messages', sa.Column('worker_id', sa.Text(), nullable=True))
    op.add_column(
        'chat_messages',
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'chat_messages',
        sa.Column('generation_claimed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_index(
        'uq_chat_messages_idempotency', 'chat_messages',
        ['idempotency_owner', 'idempotency_scope', 'idempotency_key'], unique=True,
        postgresql_where=sa.text('idempotency_key IS NOT NULL'),
    )

    op.add_column('agent_turns', sa.Column('idempotency_key', sa.Text(), nullable=True))
    op.add_column('agent_turns', sa.Column('idempotency_fingerprint', sa.Text(), nullable=True))
    op.add_column('agent_turns', sa.Column('worker_id', sa.Text(), nullable=True))
    op.add_column(
        'agent_turns',
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'uq_agent_turns_idempotency', 'agent_turns', ['session_id', 'idempotency_key'],
        unique=True, postgresql_where=sa.text('idempotency_key IS NOT NULL'),
    )

    # Old binaries cannot renew leases. Give work already in flight time to finish
    # before a new binary is allowed to recover it. The ten-minute grace exceeds
    # the configured 90-second model timeout and the 300-second Vercel function cap.
    # Marking the rows claimed (by an unknown legacy worker) keeps a new binary
    # from starting a second generation for them during the grace window.
    op.execute(
        "UPDATE chat_messages SET generation_claimed = true, "
        "lease_expires_at = clock_timestamp() + INTERVAL '10 minutes' "
        "WHERE status = 'streaming'"
    )
    op.execute(
        "UPDATE agent_turns SET lease_expires_at = clock_timestamp() + INTERVAL '10 minutes' "
        "WHERE status = 'running'"
    )


def downgrade() -> None:
    op.drop_index('uq_agent_turns_idempotency', table_name='agent_turns')
    op.drop_column('agent_turns', 'lease_expires_at')
    op.drop_column('agent_turns', 'worker_id')
    op.drop_column('agent_turns', 'idempotency_fingerprint')
    op.drop_column('agent_turns', 'idempotency_key')
    op.drop_index('uq_chat_messages_idempotency', table_name='chat_messages')
    op.drop_column('chat_messages', 'generation_claimed')
    op.drop_column('chat_messages', 'lease_expires_at')
    op.drop_column('chat_messages', 'worker_id')
    op.drop_column('chat_messages', 'idempotency_fingerprint')
    op.drop_column('chat_messages', 'idempotency_key')
    op.drop_column('chat_messages', 'idempotency_scope')
    op.drop_column('chat_messages', 'idempotency_owner')

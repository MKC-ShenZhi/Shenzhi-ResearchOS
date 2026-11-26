"""Persist runtime evidence, Worker drain, alerts and idempotent operations."""
from alembic import op
import sqlalchemy as sa

revision = '0008_management_operations'
down_revision = '0007_worker_lifecycle'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_management_runtime_evidence',
        sa.Column('run_id', sa.String(255), primary_key=True),
        sa.Column('worker_id', sa.String(255), primary_key=True),
        sa.Column('instance_id', sa.String(36), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('manifest_digest', sa.String(100)),
        sa.Column('enabled_tools', sa.JSON(), nullable=False), sa.Column('latent_tools', sa.JSON()),
        sa.Column('complete', sa.Boolean()))
    op.create_table('agent_management_worker_control',
        sa.Column('worker_id', sa.String(255), primary_key=True),
        sa.Column('draining', sa.Boolean(), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(256), nullable=False))
    op.create_table('agent_management_worker_alerts',
        sa.Column('alert_id', sa.String(100), primary_key=True),
        sa.Column('worker_id', sa.String(255), nullable=False),
        sa.Column('instance_id', sa.String(36), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(32), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recovered_at', sa.DateTime(timezone=True)),
        sa.Column('acknowledged_by', sa.String(255)), sa.Column('closed_by', sa.String(255)))
    op.create_index('ix_agent_management_worker_alerts_worker_id', 'agent_management_worker_alerts', ['worker_id'])
    op.create_index('ix_agent_management_worker_alerts_opened_at', 'agent_management_worker_alerts', ['opened_at'])
    op.create_table('agent_management_operations',
        sa.Column('operation_id', sa.String(36), primary_key=True),
        sa.Column('request_digest', sa.String(100), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False))


def downgrade():
    for table in ('agent_management_operations', 'agent_management_worker_alerts',
                  'agent_management_worker_control', 'agent_management_runtime_evidence'):
        op.drop_table(table)

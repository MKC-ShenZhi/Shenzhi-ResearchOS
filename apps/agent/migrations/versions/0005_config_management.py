"""Immutable config revisions, operation receipts and task execution constraints."""
from alembic import op
import sqlalchemy as sa

revision = '0005_config_management'
down_revision = '0004_agent_management'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_config_revisions',
        sa.Column('revision_id', sa.String(36), primary_key=True),
        sa.Column('revision_number', sa.Integer(), nullable=False, unique=True),
        sa.Column('base_revision', sa.String(36)),
        sa.Column('config_digest', sa.String(71), nullable=False),
        sa.Column('spec', sa.JSON(), nullable=False),
        sa.Column('principal', sa.String(255), nullable=False),
        sa.Column('reason', sa.String(256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('agent_config_control',
        sa.Column('name', sa.String(32), primary_key=True),
        sa.Column('active_revision', sa.String(36)),
        sa.Column('desired_revision', sa.String(36)),
        sa.Column('deployment_id', sa.String(36)),
        sa.Column('admission_paused', sa.Boolean(), nullable=False))
    op.create_table('agent_config_operations',
        sa.Column('operation_id', sa.String(36), primary_key=True),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('revision_id', sa.String(36)),
        sa.Column('fingerprint', sa.String(71), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('happened_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_agent_config_operations_revision_id', 'agent_config_operations', ['revision_id'])
    op.create_index('ix_agent_config_operations_happened_at', 'agent_config_operations', ['happened_at'])
    op.create_table('agent_task_execution_constraints',
        sa.Column('task_id', sa.String(32), primary_key=True),
        sa.Column('revision_id', sa.String(36), nullable=False),
        sa.Column('spec_digest', sa.String(71), nullable=False),
        sa.Column('build_revision', sa.String(100), nullable=False),
        sa.Column('runtime_version', sa.String(100), nullable=False),
        sa.Column('capability_manifest_digest', sa.String(71), nullable=False),
        sa.Column('required_capabilities', sa.JSON(), nullable=False),
        sa.Column('constraint_version', sa.Integer(), nullable=False))
    op.create_index('ix_agent_task_execution_constraints_revision_id', 'agent_task_execution_constraints', ['revision_id'])


def downgrade():
    # A constrained run must never be silently converted to a legacy one.
    if not op.get_context().as_sql:
        from sqlalchemy import text
        remaining = op.get_bind().execute(text('SELECT 1 FROM agent_task_execution_constraints LIMIT 1')).first()
        active = op.get_bind().execute(text(
            'SELECT 1 FROM agent_config_control WHERE active_revision IS NOT NULL OR desired_revision IS NOT NULL LIMIT 1'
        )).first()
        if remaining or active:
            raise RuntimeError('Export and drain configured execution state before removing the config schema')
    op.drop_table('agent_task_execution_constraints')
    op.drop_table('agent_config_operations')
    op.drop_table('agent_config_control')
    op.drop_table('agent_config_revisions')

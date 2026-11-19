"""Frozen A-line persistence. Downgrade only after v2 drain and audit export."""
from alembic import op
import sqlalchemy as sa

revision = '0003_agent_metering'
down_revision = '0002_agent_run_controls'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('agent_close_manifests',
    sa.Column('manifest_id', sa.String(length=255), nullable=False),
    sa.Column('task_id', sa.String(length=32), nullable=False),
    sa.Column('usage_sequence', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('ack', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.task_id'], ),
    sa.PrimaryKeyConstraint('manifest_id'),
    sa.UniqueConstraint('task_id', 'usage_sequence', name='uq_agent_close_sequence')
    )
    op.create_index(op.f('ix_agent_close_manifests_task_id'), 'agent_close_manifests', ['task_id'], unique=False)
    op.create_table('agent_grant_history',
    sa.Column('grant_id', sa.String(length=255), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.String(length=32), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.task_id'], ),
    sa.PrimaryKeyConstraint('grant_id', 'revision')
    )
    op.create_index(op.f('ix_agent_grant_history_task_id'), 'agent_grant_history', ['task_id'], unique=False)
    op.create_table('agent_grant_revocations',
    sa.Column('operation_id', sa.String(length=255), nullable=False),
    sa.Column('task_id', sa.String(length=32), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.task_id'], ),
    sa.PrimaryKeyConstraint('operation_id')
    )
    op.create_index(op.f('ix_agent_grant_revocations_task_id'), 'agent_grant_revocations', ['task_id'], unique=False)
    op.create_table('agent_task_metering',
    sa.Column('task_id', sa.String(length=32), nullable=False),
    sa.Column('owner_id', sa.String(length=255), nullable=False),
    sa.Column('submission_id', sa.String(length=255), nullable=False),
    sa.Column('profile_id', sa.String(length=255), nullable=False),
    sa.Column('context', sa.String(length=32), nullable=False),
    sa.Column('binding_status', sa.String(length=32), nullable=False),
    sa.Column('envelope', sa.JSON(), nullable=False),
    sa.Column('binding', sa.JSON(), nullable=True),
    sa.Column('receipt', sa.JSON(), nullable=True),
    sa.Column('current_grant', sa.JSON(), nullable=True),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.Column('revoked_capabilities', sa.JSON(), nullable=False),
    sa.Column('usage_sequence', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.task_id'], ),
    sa.PrimaryKeyConstraint('task_id'),
    sa.UniqueConstraint('owner_id', 'submission_id', name='uq_agent_metering_submission'),
    sa.UniqueConstraint('profile_id')
    )
    op.create_index(op.f('ix_agent_task_metering_binding_status'), 'agent_task_metering', ['binding_status'], unique=False)
    op.create_table('agent_executions',
    sa.Column('execution_id', sa.String(length=255), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('task_id', sa.String(length=32), nullable=False),
    sa.Column('worker_id', sa.String(length=255), nullable=False),
    sa.Column('lease_token', sa.Integer(), nullable=False),
    sa.Column('sealed', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['agent_runs.run_id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.task_id'], ),
    sa.PrimaryKeyConstraint('execution_id'),
    sa.UniqueConstraint('run_id', 'lease_token', name='uq_agent_execution_lease')
    )
    op.create_index(op.f('ix_agent_executions_run_id'), 'agent_executions', ['run_id'], unique=False)
    op.create_index(op.f('ix_agent_executions_task_id'), 'agent_executions', ['task_id'], unique=False)
    op.create_table('agent_calls',
    sa.Column('call_id', sa.String(length=255), nullable=False),
    sa.Column('task_id', sa.String(length=32), nullable=False),
    sa.Column('execution_id', sa.String(length=255), nullable=False),
    sa.Column('activation_key', sa.String(length=255), nullable=True),
    sa.Column('state', sa.String(length=32), nullable=False),
    sa.Column('intent', sa.JSON(), nullable=False),
    sa.Column('permit', sa.JSON(), nullable=True),
    sa.Column('backend_request', sa.JSON(), nullable=True),
    sa.Column('remote_closed', sa.Boolean(), nullable=False),
    sa.Column('start_operation_id', sa.String(length=255), nullable=True),
    sa.Column('start_fact', sa.JSON(), nullable=True),
    sa.Column('start_before', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sealed_intent', sa.JSON(), nullable=True),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['agent_executions.execution_id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.task_id'], ),
    sa.PrimaryKeyConstraint('call_id'),
    sa.UniqueConstraint('task_id', 'activation_key', name='uq_agent_skill_activation')
    )
    op.create_index(op.f('ix_agent_calls_execution_id'), 'agent_calls', ['execution_id'], unique=False)
    op.create_index(op.f('ix_agent_calls_state'), 'agent_calls', ['state'], unique=False)
    op.create_index(op.f('ix_agent_calls_task_id'), 'agent_calls', ['task_id'], unique=False)
    op.create_table('agent_usage_observations',
    sa.Column('measurement_id', sa.String(length=255), nullable=False),
    sa.Column('call_id', sa.String(length=255), nullable=False),
    sa.Column('task_id', sa.String(length=32), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('submission_key', sa.String(length=255), nullable=False),
    sa.Column('submission_digest', sa.String(length=80), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['call_id'], ['agent_calls.call_id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.task_id'], ),
    sa.PrimaryKeyConstraint('measurement_id'),
    sa.UniqueConstraint('call_id', 'revision', name='uq_agent_call_observation_revision'),
    sa.UniqueConstraint('call_id', 'submission_key', name='uq_agent_observation_submission'),
    sa.UniqueConstraint('task_id', 'sequence', name='uq_agent_task_usage_sequence')
    )
    op.create_index(op.f('ix_agent_usage_observations_call_id'), 'agent_usage_observations', ['call_id'], unique=False)
    op.create_index(op.f('ix_agent_usage_observations_task_id'), 'agent_usage_observations', ['task_id'], unique=False)
    op.create_table('agent_usage_outbox',
    sa.Column('measurement_id', sa.String(length=255), nullable=False),
    sa.Column('state', sa.String(length=32), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ack', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['measurement_id'], ['agent_usage_observations.measurement_id'], ),
    sa.PrimaryKeyConstraint('measurement_id')
    )
    op.create_index(op.f('ix_agent_usage_outbox_available_at'), 'agent_usage_outbox', ['available_at'], unique=False)
    op.create_index(op.f('ix_agent_usage_outbox_state'), 'agent_usage_outbox', ['state'], unique=False)

def downgrade():
    op.drop_table('agent_usage_outbox')
    op.drop_table('agent_usage_observations')
    op.drop_table('agent_calls')
    op.drop_table('agent_executions')
    op.drop_table('agent_task_metering')
    op.drop_table('agent_grant_revocations')
    op.drop_table('agent_grant_history')
    op.drop_table('agent_close_manifests')

"""Frozen A-line persistence. Downgrade only after v2 drain and audit export."""
from alembic import op
import sqlalchemy as sa

revision = '027_agent_entitlements'
down_revision = '026_home_scheduler_state'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('agent_entitlement_audit',
    sa.Column('audit_id', sa.String(length=255), nullable=False),
    sa.Column('operation_id', sa.String(length=255), nullable=False),
    sa.Column('principal', sa.String(length=255), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('audit_id'),
    sa.UniqueConstraint('operation_id')
    )
    op.create_table('agent_entitlement_policies',
    sa.Column('policy_revision', sa.String(length=255), nullable=False),
    sa.Column('approved', sa.Boolean(), nullable=False),
    sa.Column('test_only', sa.Boolean(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('policy_revision')
    )
    op.create_table('agent_metering_profiles',
    sa.Column('profile_id', sa.String(length=255), nullable=False),
    sa.Column('owner_id', sa.String(length=255), nullable=False),
    sa.Column('audience', sa.String(length=255), nullable=False),
    sa.Column('context', sa.String(length=32), nullable=False),
    sa.Column('provenance', sa.String(length=64), nullable=False),
    sa.Column('admission_revision', sa.String(length=255), nullable=False),
    sa.Column('request_digest', sa.String(length=80), nullable=False),
    sa.Column('client_key', sa.String(length=255), nullable=True),
    sa.Column('backend_submission_id', sa.String(length=255), nullable=True),
    sa.Column('observation_submission_id', sa.String(length=255), nullable=True),
    sa.Column('task_id', sa.String(length=255), nullable=True),
    sa.Column('enrollment_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('binding', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('profile_id'),
    sa.UniqueConstraint('audience', 'task_id', name='uq_backend_metering_task'),
    sa.UniqueConstraint('backend_submission_id'),
    sa.UniqueConstraint('observation_submission_id'),
    sa.UniqueConstraint('owner_id', 'client_key', name='uq_backend_metering_client_key')
    )
    op.create_index(op.f('ix_agent_metering_profiles_owner_id'), 'agent_metering_profiles', ['owner_id'], unique=False)
    op.create_table('agent_usage_inbox',
    sa.Column('measurement_id', sa.String(length=255), nullable=False),
    sa.Column('call_id', sa.String(length=255), nullable=False),
    sa.Column('task_id', sa.String(length=255), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('content_digest', sa.String(length=80), nullable=False),
    sa.Column('verification_status', sa.String(length=32), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('measurement_id'),
    sa.UniqueConstraint('call_id', 'revision', name='uq_backend_usage_revision'),
    sa.UniqueConstraint('task_id', 'sequence', name='uq_backend_usage_sequence')
    )
    op.create_index(op.f('ix_agent_usage_inbox_call_id'), 'agent_usage_inbox', ['call_id'], unique=False)
    op.create_index(op.f('ix_agent_usage_inbox_task_id'), 'agent_usage_inbox', ['task_id'], unique=False)
    op.create_index(op.f('ix_agent_usage_inbox_verification_status'), 'agent_usage_inbox', ['verification_status'], unique=False)
    op.create_table('agent_usage_projections',
    sa.Column('call_id', sa.String(length=255), nullable=False),
    sa.Column('task_id', sa.String(length=255), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('start_fact', sa.JSON(), nullable=False),
    sa.Column('settlement_status', sa.String(length=40), nullable=False),
    sa.PrimaryKeyConstraint('call_id')
    )
    op.create_index(op.f('ix_agent_usage_projections_task_id'), 'agent_usage_projections', ['task_id'], unique=False)
    op.create_table('agent_observation_admissions',
    sa.Column('admission_id', sa.String(length=255), nullable=False),
    sa.Column('owner_id', sa.String(length=255), nullable=False),
    sa.Column('client_key', sa.String(length=255), nullable=False),
    sa.Column('profile_id', sa.String(length=255), nullable=False),
    sa.Column('request_digest', sa.String(length=80), nullable=False),
    sa.Column('client_request_digest', sa.String(length=80), nullable=True),
    sa.Column('request', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['agent_metering_profiles.profile_id'], ),
    sa.PrimaryKeyConstraint('admission_id'),
    sa.UniqueConstraint('owner_id', 'client_key', name='uq_backend_observation_admission'),
    sa.UniqueConstraint('profile_id')
    )
    op.create_index(op.f('ix_agent_observation_admissions_owner_id'), 'agent_observation_admissions', ['owner_id'], unique=False)
    op.create_table('agent_owner_entitlements',
    sa.Column('owner_id', sa.String(length=255), nullable=False),
    sa.Column('policy_revision', sa.String(length=255), nullable=False),
    sa.Column('plan_id', sa.String(length=255), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['policy_revision'], ['agent_entitlement_policies.policy_revision'], ),
    sa.PrimaryKeyConstraint('owner_id')
    )
    op.create_table('agent_entitlement_windows',
    sa.Column('window_id', sa.String(length=255), nullable=False),
    sa.Column('owner_id', sa.String(length=255), nullable=False),
    sa.Column('rule_id', sa.String(length=255), nullable=False),
    sa.Column('window_ref', sa.JSON(), nullable=False),
    sa.Column('limit_units', sa.BigInteger(), nullable=False),
    sa.Column('held', sa.BigInteger(), nullable=False),
    sa.Column('used', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('held >= 0 AND used >= 0', name='ck_backend_window_nonnegative'),
    sa.ForeignKeyConstraint(['owner_id'], ['agent_owner_entitlements.owner_id'], ),
    sa.PrimaryKeyConstraint('window_id')
    )
    op.create_index(op.f('ix_agent_entitlement_windows_owner_id'), 'agent_entitlement_windows', ['owner_id'], unique=False)
    op.create_index(op.f('ix_agent_entitlement_windows_rule_id'), 'agent_entitlement_windows', ['rule_id'], unique=False)
    op.create_table('agent_submissions',
    sa.Column('submission_id', sa.String(length=255), nullable=False),
    sa.Column('owner_id', sa.String(length=255), nullable=False),
    sa.Column('client_key', sa.String(length=255), nullable=False),
    sa.Column('request_digest', sa.String(length=80), nullable=False),
    sa.Column('request', sa.JSON(), nullable=False),
    sa.Column('client_request_digest', sa.String(length=80), nullable=True),
    sa.Column('profile_id', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['agent_owner_entitlements.owner_id'], ),
    sa.ForeignKeyConstraint(['profile_id'], ['agent_metering_profiles.profile_id'], ),
    sa.PrimaryKeyConstraint('submission_id'),
    sa.UniqueConstraint('owner_id', 'client_key', name='uq_backend_submission_key'),
    sa.UniqueConstraint('profile_id')
    )
    op.create_index(op.f('ix_agent_submissions_owner_id'), 'agent_submissions', ['owner_id'], unique=False)
    op.create_index(op.f('ix_agent_submissions_status'), 'agent_submissions', ['status'], unique=False)
    op.create_table('agent_grant_roots',
    sa.Column('grant_id', sa.String(length=255), nullable=False),
    sa.Column('submission_id', sa.String(length=255), nullable=False),
    sa.Column('reservation_id', sa.String(length=255), nullable=False),
    sa.Column('current_revision', sa.Integer(), nullable=False),
    sa.Column('binding_revision', sa.Integer(), nullable=False),
    sa.Column('bound_task_id', sa.String(length=255), nullable=True),
    sa.Column('receipt', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('settlement_status', sa.String(length=40), nullable=False),
    sa.Column('overage', sa.Boolean(), nullable=False),
    sa.Column('revoked_capabilities', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['submission_id'], ['agent_submissions.submission_id'], ),
    sa.PrimaryKeyConstraint('grant_id'),
    sa.UniqueConstraint('bound_task_id'),
    sa.UniqueConstraint('reservation_id'),
    sa.UniqueConstraint('submission_id')
    )
    op.create_index(op.f('ix_agent_grant_roots_status'), 'agent_grant_roots', ['status'], unique=False)
    op.create_table('agent_call_permits',
    sa.Column('permit_id', sa.String(length=255), nullable=False),
    sa.Column('audience', sa.String(length=255), nullable=False),
    sa.Column('call_id', sa.String(length=255), nullable=False),
    sa.Column('grant_id', sa.String(length=255), nullable=False),
    sa.Column('request_digest', sa.String(length=80), nullable=False),
    sa.Column('request', sa.JSON(), nullable=False),
    sa.Column('response', sa.JSON(), nullable=False),
    sa.Column('state', sa.String(length=32), nullable=False),
    sa.Column('held', sa.JSON(), nullable=False),
    sa.Column('adopted', sa.JSON(), nullable=False),
    sa.Column('start', sa.JSON(), nullable=True),
    sa.Column('void_proof', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['grant_id'], ['agent_grant_roots.grant_id'], ),
    sa.PrimaryKeyConstraint('permit_id'),
    sa.UniqueConstraint('audience', 'call_id', name='uq_backend_permit_call')
    )
    op.create_index(op.f('ix_agent_call_permits_call_id'), 'agent_call_permits', ['call_id'], unique=False)
    op.create_index(op.f('ix_agent_call_permits_grant_id'), 'agent_call_permits', ['grant_id'], unique=False)
    op.create_index(op.f('ix_agent_call_permits_state'), 'agent_call_permits', ['state'], unique=False)
    op.create_table('agent_grant_revisions',
    sa.Column('grant_id', sa.String(length=255), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('payload_digest', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['grant_id'], ['agent_grant_roots.grant_id'], ),
    sa.PrimaryKeyConstraint('grant_id', 'revision')
    )
    op.create_table('agent_reservation_allocations',
    sa.Column('allocation_id', sa.String(length=255), nullable=False),
    sa.Column('grant_id', sa.String(length=255), nullable=False),
    sa.Column('window_id', sa.String(length=255), nullable=False),
    sa.Column('allocation', sa.JSON(), nullable=False),
    sa.Column('task_held', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('task_held >= 0', name='ck_backend_reservation_nonnegative'),
    sa.ForeignKeyConstraint(['grant_id'], ['agent_grant_roots.grant_id'], ),
    sa.ForeignKeyConstraint(['window_id'], ['agent_entitlement_windows.window_id'], ),
    sa.PrimaryKeyConstraint('allocation_id')
    )
    op.create_index(op.f('ix_agent_reservation_allocations_grant_id'), 'agent_reservation_allocations', ['grant_id'], unique=False)
    op.create_index(op.f('ix_agent_reservation_allocations_window_id'), 'agent_reservation_allocations', ['window_id'], unique=False)
    op.create_table('agent_task_closes',
    sa.Column('manifest_id', sa.String(length=255), nullable=False),
    sa.Column('grant_id', sa.String(length=255), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.ForeignKeyConstraint(['grant_id'], ['agent_grant_roots.grant_id'], ),
    sa.PrimaryKeyConstraint('manifest_id')
    )
    op.create_index(op.f('ix_agent_task_closes_grant_id'), 'agent_task_closes', ['grant_id'], unique=False)
    op.create_table('agent_usage_ledger',
    sa.Column('entry_id', sa.String(length=255), nullable=False),
    sa.Column('operation_key', sa.String(length=255), nullable=False),
    sa.Column('owner_id', sa.String(length=255), nullable=False),
    sa.Column('grant_id', sa.String(length=255), nullable=False),
    sa.Column('allocation_id', sa.String(length=255), nullable=False),
    sa.Column('measurement_id', sa.String(length=255), nullable=True),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('held_delta', sa.BigInteger(), nullable=False),
    sa.Column('used_delta', sa.BigInteger(), nullable=False),
    sa.Column('evidence', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['allocation_id'], ['agent_reservation_allocations.allocation_id'], ),
    sa.ForeignKeyConstraint(['grant_id'], ['agent_grant_roots.grant_id'], ),
    sa.ForeignKeyConstraint(['measurement_id'], ['agent_usage_inbox.measurement_id'], ),
    sa.PrimaryKeyConstraint('entry_id'),
    sa.UniqueConstraint('operation_key')
    )
    op.create_index(op.f('ix_agent_usage_ledger_allocation_id'), 'agent_usage_ledger', ['allocation_id'], unique=False)
    op.create_index(op.f('ix_agent_usage_ledger_grant_id'), 'agent_usage_ledger', ['grant_id'], unique=False)
    op.create_index(op.f('ix_agent_usage_ledger_owner_id'), 'agent_usage_ledger', ['owner_id'], unique=False)

def downgrade():
    op.drop_table('agent_usage_ledger')
    op.drop_table('agent_task_closes')
    op.drop_table('agent_reservation_allocations')
    op.drop_table('agent_grant_revisions')
    op.drop_table('agent_call_permits')
    op.drop_table('agent_grant_roots')
    op.drop_table('agent_submissions')
    op.drop_table('agent_entitlement_windows')
    op.drop_table('agent_owner_entitlements')
    op.drop_table('agent_observation_admissions')
    op.drop_table('agent_usage_projections')
    op.drop_table('agent_usage_inbox')
    op.drop_table('agent_metering_profiles')
    op.drop_table('agent_entitlement_policies')
    op.drop_table('agent_entitlement_audit')

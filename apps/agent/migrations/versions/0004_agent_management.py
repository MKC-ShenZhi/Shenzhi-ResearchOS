"""Worker management evidence. No execution or lease schema changes."""
from alembic import op
import sqlalchemy as sa

revision = '0004_agent_management'
down_revision = '0003_agent_metering'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_management_worker_instances',
        sa.Column('worker_id', sa.String(255), primary_key=True),
        sa.Column('instance_id', sa.String(36), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('request_digest', sa.String(100), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lifecycle', sa.String(16), nullable=False),
        sa.Column('health', sa.String(16), nullable=False),
        sa.Column('active_run_id', sa.String(255)),
        sa.Column('run_tool_ids', sa.JSON(), nullable=False),
        sa.Column('manifest_digest', sa.String(100)))
    op.create_index('ix_agent_management_worker_instances_observed_at', 'agent_management_worker_instances', ['observed_at'])
    op.create_table('agent_management_worker_manifests',
        sa.Column('worker_id', sa.String(255), primary_key=True),
        sa.Column('digest', sa.String(100), primary_key=True),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_agent_management_worker_manifests_last_seen', 'agent_management_worker_manifests', ['last_seen'])


def downgrade():
    op.drop_table('agent_management_worker_manifests')
    op.drop_table('agent_management_worker_instances')

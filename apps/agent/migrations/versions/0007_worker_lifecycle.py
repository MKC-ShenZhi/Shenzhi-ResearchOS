"""Retain Worker lifecycle transitions from authenticated reports."""
from alembic import op
import sqlalchemy as sa

revision = '0007_worker_lifecycle'
down_revision = '0006_config_fencing'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_management_worker_events',
                    sa.Column('worker_id', sa.String(255), primary_key=True),
                    sa.Column('instance_id', sa.String(36), primary_key=True),
                    sa.Column('sequence', sa.Integer(), primary_key=True),
                    sa.Column('kind', sa.String(32), primary_key=True),
                    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('manifest_digest', sa.String(100)),
                    sa.Column('run_id', sa.String(255)))
    op.create_index('ix_agent_management_worker_events_observed_at', 'agent_management_worker_events', ['observed_at'])


def downgrade():
    op.drop_table('agent_management_worker_events')

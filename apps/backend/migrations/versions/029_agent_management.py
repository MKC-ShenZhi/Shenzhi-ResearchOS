"""Independent Agent management audit and health history."""
from alembic import op
import sqlalchemy as sa

revision = '029_agent_management'
down_revision = '028_formal_plans'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_management_audit',
        sa.Column('audit_id', sa.String(36), primary_key=True),
        sa.Column('request_id', sa.String(36), nullable=False),
        sa.Column('online_probe', sa.Boolean(), nullable=False),
        sa.Column('principal', sa.String(255), nullable=False),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('target_kind', sa.String(16), nullable=False),
        sa.Column('target_id', sa.String(255), nullable=False),
        sa.Column('target_fingerprint', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_digest', sa.String(100), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('reason', sa.String(100)),
        sa.Column('reserved_tokens', sa.Integer(), nullable=False),
        sa.Column('outcome', sa.JSON()),
        sa.Column('seal', sa.String(64), nullable=False))
    op.create_index('ix_agent_management_audit_created_at', 'agent_management_audit', ['created_at'])


def downgrade():
    op.drop_table('agent_management_audit')

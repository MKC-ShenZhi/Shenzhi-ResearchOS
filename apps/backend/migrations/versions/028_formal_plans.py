"""Formal plan publication pointers. No historical policy/usage rewrite."""
from alembic import op
import sqlalchemy as sa
revision = '028_formal_plans'
down_revision = '027_agent_entitlements'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_plan_releases',
        sa.Column('plan_id', sa.String(255), primary_key=True),
        sa.Column('policy_revision', sa.String(255), sa.ForeignKey('agent_entitlement_policies.policy_revision'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('agent_plan_releases')

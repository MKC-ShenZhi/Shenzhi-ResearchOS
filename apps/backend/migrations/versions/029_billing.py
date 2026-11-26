"""Subscription expiry and durable payment/fulfillment records."""
from alembic import op
import sqlalchemy as sa

revision = '029_billing'
down_revision = '028_formal_plans'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_owner_entitlements', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agent_owner_entitlements', sa.Column('source', sa.String(32), nullable=False, server_default='admin'))
    op.create_table('billing_orders',
        sa.Column('order_id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(255), nullable=False, index=True),
        sa.Column('plan_id', sa.String(32), nullable=False),
        sa.Column('policy_revision', sa.String(255), sa.ForeignKey('agent_entitlement_policies.policy_revision'), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('channel', sa.String(16), nullable=False),
        sa.Column('mode', sa.String(16), nullable=False),
        sa.Column('merchant_id', sa.String(255), nullable=False),
        sa.Column('app_id', sa.String(255), nullable=False),
        sa.Column('payment_status', sa.String(16), nullable=False),
        sa.Column('fulfillment_status', sa.String(16), nullable=False),
        sa.Column('fulfillment_error', sa.String(255)),
        sa.Column('transaction_id', sa.String(128)),
        sa.Column('payment', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True)),
        sa.Column('fulfilled_at', sa.DateTime(timezone=True)),
        sa.Column('subscription_expires_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('amount > 0', name='ck_billing_amount_positive'),
        sa.UniqueConstraint('channel', 'mode', 'transaction_id', name='uq_billing_transaction'))


def downgrade():
    op.drop_table('billing_orders')
    op.drop_column('agent_owner_entitlements', 'source')
    op.drop_column('agent_owner_entitlements', 'expires_at')

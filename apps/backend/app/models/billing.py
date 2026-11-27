"""Business orders; provider calls never own entitlement state."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class BillingOrderRow(Base):
    __tablename__ = 'billing_orders'
    __table_args__ = (
        CheckConstraint('amount > 0', name='ck_billing_amount_positive'),
        UniqueConstraint('channel', 'mode', 'transaction_id', name='uq_billing_transaction'),
    )
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    plan_id: Mapped[str] = mapped_column(String(32))
    policy_revision: Mapped[str] = mapped_column(ForeignKey('agent_entitlement_policies.policy_revision'))
    snapshot: Mapped[dict] = mapped_column(JSON)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    channel: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))
    merchant_id: Mapped[str] = mapped_column(String(255))
    app_id: Mapped[str] = mapped_column(String(255))
    payment_status: Mapped[str] = mapped_column(String(16), default='pending')
    fulfillment_status: Mapped[str] = mapped_column(String(16), default='pending')
    fulfillment_error: Mapped[str | None] = mapped_column(String(255))
    transaction_id: Mapped[str | None] = mapped_column(String(128))
    payment: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

"""Add authenticated user preference storage."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '003_user_settings'
down_revision: Union[str, Sequence[str], None] = '002_anon_expiry_idx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.Text(), primary_key=True),
        sa.Column('locale', sa.Text(), nullable=False, server_default=sa.text("'zh-CN'")),
        sa.Column('theme_mode', sa.Text(), nullable=False, server_default=sa.text("'system'")),
        sa.Column('notify_activity', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_subscription', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_interaction', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_system', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("locale IN ('zh-CN', 'en')", name='chk_user_settings_locale'),
        sa.CheckConstraint("theme_mode IN ('light', 'dark', 'system')", name='chk_user_settings_theme_mode'),
    )


def downgrade() -> None:
    op.drop_table('user_settings')

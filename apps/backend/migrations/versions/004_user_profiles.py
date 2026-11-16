"""Add authenticated personal profiles."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '004_user_profiles'
down_revision: Union[str, Sequence[str], None] = '003_user_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_profiles',
        sa.Column('user_id', sa.Text(), primary_key=True),
        sa.Column('avatar_key', sa.Text(), nullable=False),
        sa.Column('avatar_selected', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('bio', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('achievements', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('educations', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('biography', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('institutions', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(
            "avatar_key IN ('avatar-01', 'avatar-02', 'avatar-03', 'avatar-04', 'avatar-05')",
            name='chk_user_profiles_avatar_key',
        ),
    )


def downgrade() -> None:
    op.drop_table('user_profiles')

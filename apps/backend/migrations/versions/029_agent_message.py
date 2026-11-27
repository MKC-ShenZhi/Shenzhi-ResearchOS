"""Store Agent message v1 snapshots; existing turns keep SQL NULL."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '029_agent_message'
down_revision = '028_formal_plans'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_turns', sa.Column('message', postgresql.JSONB(none_as_null=True), nullable=True))


def downgrade():
    op.drop_column('agent_turns', 'message')

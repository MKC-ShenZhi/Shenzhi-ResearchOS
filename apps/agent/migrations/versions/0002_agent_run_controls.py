"""Persist runtime steering controls for active Agent runs."""
from alembic import op

from agent_app.infrastructure.models import Base

revision = '0002_agent_run_controls'
down_revision = '0001_agent_task_run_event_outbox'
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(),
                              tables=[Base.metadata.tables['agent_run_controls']])


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(),
                           tables=[Base.metadata.tables['agent_run_controls']])

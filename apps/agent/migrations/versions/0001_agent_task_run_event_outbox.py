"""Agent-owned Task, Run, Event and Outbox persistence."""
from alembic import op

from agent_app.infrastructure.models import Base

revision = '0001_agent_task_run_event_outbox'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_names = ('agent_tasks', 'agent_runs', 'agent_run_events', 'agent_outbox')
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[name]
                                                       for name in table_names])


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

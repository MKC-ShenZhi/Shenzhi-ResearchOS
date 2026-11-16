"""Current conference snapshot and durable sync/check timestamps."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "022_conference_snapshots"
down_revision = "021_conference_follow_ids"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "conference_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("snapshot_id", sa.Text()),
        sa.Column("upstream_sha", sa.Text()),
        sa.Column("data_as_of", sa.Date()),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("id = 1", name="conference_snapshot_singleton"),
    )


def downgrade():
    op.drop_table("conference_snapshots")

"""Preserve conference follows after upstream category changes."""

from alembic import op
import sqlalchemy as sa

revision = "021_conference_follow_ids"
down_revision = "020_snapshot_complete"
branch_labels = depends_on = None


def upgrade():
    for old, new in (("ds-dcc", "cg-dcc"), ("se-eusipco", "cg-eusipco")):
        op.execute(
            sa.text("""INSERT INTO conference_follows (user_id, conference_id, created_at)
            SELECT user_id, :new, created_at FROM conference_follows WHERE conference_id = :old
            ON CONFLICT (user_id, conference_id) DO NOTHING""").bindparams(
                old=old, new=new
            )
        )
        op.execute(
            sa.text(
                "DELETE FROM conference_follows WHERE conference_id = :old"
            ).bindparams(old=old)
        )


def downgrade():
    # Many-to-one merge cannot be reversed without inventing users' old choices.
    pass

"""Join independently developed Chat cleanup and conference snapshot revisions.

No data changes: keep existing revision IDs usable for databases that already
ran either branch. Alembic applies the missing branch before reaching this head.
"""
revision = "023_merge_conference_chat"
down_revision = ("021_drop_chat_tables", "022_conference_snapshots")
branch_labels = depends_on = None

def upgrade():
    pass

def downgrade():
    pass

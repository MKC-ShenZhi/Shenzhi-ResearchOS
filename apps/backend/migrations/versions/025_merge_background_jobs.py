"""Join the discovery topics and knowledge conference snapshot revisions."""

revision = '025_merge_background_jobs'
down_revision = ('024_discovery_pool_topics', '024_knowledge_venue_snapshot')
branch_labels = depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

"""Serialize entitlement compatibility writes with an Agent config handoff."""
from alembic import op
import sqlalchemy as sa

revision = '030_agent_config_barrier'
down_revision = '029_agent_management'
branch_labels = None
depends_on = None

TRIGGERS = {
    'agent_entitlement_policies': 'INSERT OR UPDATE OR DELETE',
    'agent_plan_releases': 'INSERT OR UPDATE OR DELETE',
    'agent_owner_entitlements': 'INSERT OR UPDATE OR DELETE',
    'agent_grant_roots': 'INSERT OR UPDATE OF current_revision',
    'agent_grant_revisions': 'INSERT OR UPDATE OR DELETE',
}


def upgrade():
    op.create_table('agent_config_entitlement_barrier',
                    sa.Column('name', sa.String(20), primary_key=True),
                    sa.Column('deployment_id', sa.String(36), nullable=False),
                    sa.Column('operation_id', sa.String(36), nullable=False))
    op.execute("""
        CREATE FUNCTION check_agent_config_entitlement_barrier() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock_shared(739201132);
            IF EXISTS (SELECT 1 FROM agent_config_entitlement_barrier WHERE name = 'publish') THEN
                RAISE EXCEPTION 'agent configuration handoff is pending'
                    USING ERRCODE = '55P03';
            END IF;
            RETURN NULL;
        END;
        $$
    """)
    for table, events in TRIGGERS.items():
        op.execute(f'CREATE TRIGGER config_entitlement_barrier BEFORE {events} ON {table} '
                   'FOR EACH STATEMENT EXECUTE FUNCTION check_agent_config_entitlement_barrier()')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM agent_config_entitlement_barrier LIMIT 1')).first():
        raise RuntimeError('Reconcile the active configuration handoff before removing its barrier')
    for table in TRIGGERS:
        op.execute(f'DROP TRIGGER config_entitlement_barrier ON {table}')
    op.execute('DROP FUNCTION check_agent_config_entitlement_barrier()')
    op.drop_table('agent_config_entitlement_barrier')

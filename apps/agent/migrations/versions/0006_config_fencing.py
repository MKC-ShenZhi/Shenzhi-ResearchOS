"""Persist the release generation and ownership of the admission pause."""
from alembic import op
import sqlalchemy as sa

revision = '0006_config_fencing'
down_revision = '0005_config_management'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_config_control', sa.Column('fencing_token', sa.BigInteger(), server_default='0', nullable=False))
    op.add_column('agent_config_control', sa.Column('pause_operation_id', sa.String(36)))
    op.add_column('agent_config_control', sa.Column('pause_reason', sa.String(256)))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text(
        'SELECT 1 FROM agent_config_control WHERE admission_paused OR fencing_token > 0 LIMIT 1'
    )).first():
        raise RuntimeError('Keep the release fence and admission state until the deployment is retired')
    op.drop_column('agent_config_control', 'pause_reason')
    op.drop_column('agent_config_control', 'pause_operation_id')
    op.drop_column('agent_config_control', 'fencing_token')

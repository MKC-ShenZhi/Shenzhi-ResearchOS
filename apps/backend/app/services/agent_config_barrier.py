"""PostgreSQL handoff barrier for the writes included in compatibility checks."""
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import get_session_factory
from app.core.errors import BusinessError


async def pending():
    async with get_session_factory()() as db:
        if db.bind.dialect.name != 'postgresql':
            return None
        record = (await db.execute(text(
            "SELECT deployment_id, operation_id FROM agent_config_entitlement_barrier WHERE name = 'publish'"
        ))).first()
        return tuple(record) if record else None


def handoff_conflict(error):
    error = error.orig if isinstance(error, DBAPIError) else error
    return getattr(error, 'sqlstate', None) == '55P03' and 'agent configuration handoff is pending' in str(error)


async def barrier(deployment_id, operation_id, *, release=False, abort=False, factory=None):
    async with (factory or get_session_factory())() as db, db.begin():
        if db.bind.dialect.name != 'postgresql':
            return
        await db.execute(text("SET LOCAL lock_timeout = '2000ms'"))
        if release:
            await db.execute(text('SELECT pg_advisory_xact_lock(739201132)'))
        elif not await db.scalar(text('SELECT pg_try_advisory_xact_lock(739201132)')):
            raise BusinessError(10001, 'CONFIG_ENTITLEMENT_WRITES_BUSY', 409)
        prior = (await db.execute(text(
            "SELECT deployment_id, operation_id FROM agent_config_entitlement_barrier WHERE name = 'publish'"
        ))).first()
        if release:
            if prior and prior.deployment_id == deployment_id and (abort or prior.operation_id == operation_id):
                await db.execute(text("DELETE FROM agent_config_entitlement_barrier WHERE name = 'publish'"))
        elif not prior:
            await db.execute(text(
                "INSERT INTO agent_config_entitlement_barrier VALUES ('publish', :deployment, :operation)"
            ), {'deployment': deployment_id, 'operation': operation_id})
        elif (prior.deployment_id, prior.operation_id) != (deployment_id, operation_id):
            raise BusinessError(10001, 'CONFIG_ENTITLEMENT_HANDOFF_PENDING', 409)

"""Periodic read-only reconciliation of durable Agent release and Backend audit evidence."""
import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from agent_contracts.management_config import ConfigIndex, Operation
from app.core.errors import BusinessError
from . import agent_config_management as config, agent_management_audit as audit
from .agent_config_barrier import barrier, pending

log = logging.getLogger(__name__)


async def inspect_release():
    index = await config.read('/revisions', ConfigIndex)
    deployment = index.deployment
    if not deployment:
        return {'state': 'idle', 'pause_operation_id': index.pause_operation_id}
    problems = list(deployment.blockers)
    try:
        entries = await audit.rows(0, 1, audit_id=str(deployment.operation_id))
    except BusinessError as error:
        problems.append('BACKEND_AUDIT_MISSING' if error.status == 404 else 'BACKEND_AUDIT_UNKNOWN')
    else:
        if not entries:
            problems.append('BACKEND_AUDIT_MISSING')
        elif entries[0].state in ('unknown', 'pending'):
            problems.append('BACKEND_AUDIT_PENDING')
    if deployment.status in ('deploying', 'partially_deployed', 'pending_reconcile', 'rollback_pending'):
        if index.desired_revision != deployment.revision_id:
            problems.append('DESIRED_REVISION_MISMATCH')
        if deployment.fencing_token is not None and not index.admission_paused:
            problems.append('ADMISSION_PAUSE_MISSING')
    elif deployment.status in ('active', 'rolled_back') and index.active_revision != deployment.revision_id:
        problems.append('ACTIVE_REVISION_MISMATCH')
    return {'state': deployment.status, 'operation_id': deployment.operation_id, 'problems': problems,
            'active_revision': index.active_revision, 'desired_revision': index.desired_revision,
            'pause_operation_id': index.pause_operation_id}


async def recover_handoff():
    handoff = await pending()
    if not handoff:
        return
    deployment_id, operation_id = handoff
    try:
        receipt = await config.read('/operations/' + operation_id, Operation, {'original': 'true'})
    except BusinessError as error:
        if error.status != 404:
            raise
        deployment = await config.read('/operations/' + deployment_id, Operation)
        if deployment.status == 'paused':
            await barrier(deployment_id, operation_id, release=True, abort=True)
        return
    if receipt.action == 'reconcile' and str(receipt.revision_id) == deployment_id:
        await barrier(deployment_id, operation_id, release=True)
        await config.finish(receipt)


async def watch():
    prior = None
    while True:
        try:
            await recover_handoff()
            report = await inspect_release()
        except (BusinessError, SQLAlchemyError, OSError, RuntimeError):
            report = {'state': 'unknown', 'problems': ['CONFIG_RECONCILIATION_UNAVAILABLE']}
        if report != prior:
            log.info('Agent configuration reconciliation %s', report)
            prior = report
        await asyncio.sleep(30)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(watch())

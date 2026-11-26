"""Audited administrator control through existing Agent execution boundaries."""
from pydantic import RootModel
from agent_contracts.management import Task, Run
from app.core.errors import BusinessError
from app.integrations import agent_management as agent
from app.services.agent_gateway.v2 import AgentGatewayV2
from . import agent_management_audit as audit


async def cancellation_status(kind, target):
    if kind == 'run':
        run = await agent.read(agent.management_path('/runs/{id}', {'id': target}), Run, {})
        task_id = run.task_id
    else:
        task_id = target
    task = await agent.read(agent.management_path('/tasks/{id}', {'id': task_id}), Task, {})
    entries = await audit.rows(0, 1, action='control', target_kind=kind, target_id=target)
    requested = entries[0].created_at if entries else None
    state = 'not_requested'
    if task.cancel_requested:
        state = 'confirmed' if task.status == 'cancelled' else 'pending'
        if task.status in ('completed', 'failed'):
            state = 'finished_with_other_result'
        elif state == 'pending' and requested and (audit.now() - requested).total_seconds() > 120:
            state = 'timed_out'
    return dict(target_id=target, task_id=task_id, task_status=task.status,
                cancellation=state, requested_at=requested.isoformat() if requested else None,
                current_run=task.latest_run.run_id if task.latest_run else None,
                execution_sealed=task.latest_run.execution.sealed if task.latest_run and task.latest_run.execution else None)


async def perform(body, principal, request_id):
    prior = await audit.admit(principal, 'control', body, request_id)
    if prior and prior.state == 'pass':
        return prior.config_event
    if prior and prior.state == 'fail':
        raise BusinessError(20001, 'CONTROL_PREVIOUSLY_REJECTED', 409)
    try:
        if body.action == 'cancel' and body.kind in ('task', 'run'):
            target = body.target_id
            if body.kind == 'run':
                run = await agent.read(agent.management_path('/runs/{id}', {'id': target}), Run, {})
                target = run.task_id
            task = await agent.read(agent.management_path('/tasks/{id}', {'id': target}), Task, {})
            if body.kind == 'run' and (not task.latest_run or task.latest_run.run_id != body.target_id):
                raise BusinessError(20001, 'RUN_IS_NOT_CURRENT', 409)
            # Owner comes from trusted Agent evidence, never from the browser.
            gateway = AgentGatewayV2()
            if body.kind == 'run':
                result = await gateway.cancel(task.task_id, task.owner_id, expected_run_id=body.target_id)
            else:
                result = await gateway.cancel(task.task_id, task.owner_id)
            data = dict(target_id=body.target_id, action='cancel', state=result.get('status', 'unknown'),
                        task_id=task.task_id, operation_id=str(body.operation_id),
                        worker_confirmation='Inspect Task and Execution for terminal cancellation')
        else:
            result = await agent.request('POST', '/config/actions', RootModel[dict], config_role=True,
                payload={**body.model_dump(mode='json'), 'actor': principal})
            data = result.root
        await audit.complete(body.operation_id, 'pass', 'CONTROL_ACCEPTED', data,
                             verified_target=True, reopen_unknown=True)
        return data
    except BusinessError as error:
        await audit.complete(body.operation_id, 'fail' if error.status < 500 else 'unknown',
            'CONTROL_REJECTED' if error.status < 500 else 'CONTROL_RESULT_UNCONFIRMED', reopen_unknown=True)
        raise

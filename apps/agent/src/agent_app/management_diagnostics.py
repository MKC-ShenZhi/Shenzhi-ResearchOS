"""Classification from allow-listed management evidence."""
from agent_contracts.management_phase2 import DiagnosticResult
from agent_app.control.metering import GateDenied, now_utc
from agent_app.management_observations import latest_model_observation, latest_tool_call, run_detail, task_detail
from agent_app.management_workers import list_workers, revision


async def diagnose(kind, target_id):
    fields = dict(kind=kind, target_id=target_id, observed_at=now_utc(), source='agent_api',
                  reason='NO_FAILURE_EVIDENCE', build_revision=revision('AGENT_BUILD_REVISION'),
                  config_revision=revision('AGENT_CONFIG_REVISION'))
    if kind == 'worker':
        workers = await list_workers(0, 1, target_id, include_manifest=True)
        if not workers:
            raise GateDenied('WORKER_NOT_OBSERVED', 404)
        worker = workers[0]
        fields.update(reason='WORKER_' + worker.state.upper(), worker_id=worker.worker_id,
                      run_id=worker.active_run_id, occurred_at=worker.observed_at,
                      build_revision=worker.manifest.build_revision if worker.manifest else None,
                      config_revision=worker.manifest.config_revision if worker.manifest else None,
                      source='worker_heartbeat')
    elif kind in ('run', 'task'):
        run = await run_detail(target_id) if kind == 'run' else (await task_detail(target_id)).latest_run
        if run:
            fields.update(reason=run.error_code or ('LEASE_EXPIRED' if run.lease_status == 'expired' else 'NO_FAILURE_EVIDENCE'),
                          worker_id=run.worker_id, run_id=run.run_id,
                          occurred_at=run.completed_at or run.started_at, source='run_metadata',
                          build_revision=None, config_revision=None)
    elif kind in ('model', 'provider'):
        reported = await latest_model_observation(**{kind + '_id': target_id})
        if reported:
            fields.update(reason='MODEL_CALL_' + reported.outcome.upper(), occurred_at=reported.observed_at,
                          source='usage_observation', build_revision=None, config_revision=None)
    elif kind == 'tool':
        call = await latest_tool_call(target_id)
        if call:
            state = call.status if call.status in ('started', 'completed', 'failed', 'denied', 'void') else 'unknown'
            run = await run_detail(call.run_id)
            fields.update(reason='TOOL_CALL_' + state.upper(), call_id=call.call_id, run_id=run.run_id,
                          occurred_at=call.started_at, source='call_metadata', worker_id=run.worker_id,
                          build_revision=None, config_revision=None)
    else:
        from types import SimpleNamespace
        from agent_app.management_checks import check
        data = await check(SimpleNamespace(kind='skill', target_id=target_id, profile='static'))
        fields['reason'] = data.reason
    return DiagnosticResult(**fields)

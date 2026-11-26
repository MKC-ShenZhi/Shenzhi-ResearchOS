"""Poll durable Agent runs, execute one Runtime attempt, and report through Agent API."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from agent_contracts import WorkerHeartbeatRequestWire, WorkerHeartbeatResponseWire

from agent_app.application.composition import build_runtime
from agent_app.application.policies import MAX_EXECUTION_TURNS, run_deadline_s, tool_call_budget
from agent_app.errors import BusinessError
from agent_app.execution.types import (
    TOOL_CALL, TOOL_END, AgentEvent, RunChannel, RunResult, StopReason, UserMessage, message_from_dict, message_to_dict,
)
from agent_app.extensions.workspace import Workspace, ensure_session_workspace, read_session_file

logger = logging.getLogger('agent.worker')


class AgentControlClient:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        base = os.getenv('AGENT_INTERNAL_URL', 'http://127.0.0.1:8101').rstrip('/')
        self.execution_id = None
        token = os.getenv('AGENT_WORKER_TOKEN', '').strip()
        if not token:
            raise RuntimeError('AGENT_WORKER_TOKEN is required by Agent Worker protocol v2')
        self.client = httpx.AsyncClient(base_url=base, timeout=20, transport=transport,
                                        headers={'Authorization': f'Bearer {token}'})

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path.startswith('/internal/v2/'):
            body = dict(body, schema_version=1)
            if '/worker/claim' not in path and self.execution_id is not None:
                body.setdefault('execution_id', self.execution_id)
        response = await self.client.post(path, json=body)
        if response.is_error:
            try:
                error = response.json().get('error', {})
                reason = error.get('reason_code')
            except (ValueError, AttributeError):
                reason = None
            if isinstance(reason, str):
                raise BusinessError(20004, reason, response.status_code)
        response.raise_for_status()
        return response.json()

    async def get(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def claim(self, worker_id: str):
        claim = await self.post('/internal/v2/worker/claim', {
            'schema_version': 1, 'worker_id': worker_id,
            'demo_mode': os.getenv('AGENT_DEMO_MODE') == '1',
        })
        if claim.get('run') is not None:
            self.execution_id = claim['execution_id']
        return claim

    async def heartbeat(self, run_id: str, worker_id: str,
                        lease_token: int) -> WorkerHeartbeatResponseWire:
        request = WorkerHeartbeatRequestWire(worker_id=worker_id, lease_token=lease_token)
        response = await self.post(
            f'/internal/v2/runs/{run_id}/heartbeat', request.model_dump(mode='json'),
        )
        response.pop('schema_version', None)
        return WorkerHeartbeatResponseWire.model_validate(response)

    async def close(self) -> None:
        await self.client.aclose()


_MARKDOWN_SUFFIXES = {'.md', '.markdown'}


class ReportFileOperations:
    """Track successful Markdown operations for a single Worker execution."""

    def __init__(self) -> None:
        self._calls: dict[tuple[int, str], tuple[str, str] | None] = {}
        self._successful: dict[tuple[int, str], str] = {}

    def observe(self, event: AgentEvent) -> None:
        if event.name not in (TOOL_CALL, TOOL_END):
            return
        call_id = event.data.get('tool_call_id')
        if not isinstance(call_id, str) or not call_id:
            return
        key = (event.turn, call_id)
        name = event.data.get('name')
        if event.name == TOOL_CALL:
            if key in self._calls:
                # Even a non-file call can make this key ambiguous.
                self._calls[key] = None
                self._successful.pop(key, None)
                return
            self._calls[key] = None
            if name not in ('write_file', 'edit_file'):
                return
            arguments = json.loads(event.data['arguments'])
            path = arguments.get('path') if isinstance(arguments, dict) else None
            if isinstance(path, str) and Path(path).suffix.lower() in _MARKDOWN_SUFFIXES:
                self._calls[key] = (name, path)
            return

        call = self._calls.get(key)
        if call is None or call[0] != name:
            return
        self._calls[key] = None
        if event.data.get('is_error') is False:
            self._successful[key] = call[1]

    def latest_path(self) -> str | None:
        return next(reversed(self._successful.values()), None)


def attach_report_output(request: dict[str, Any], result: RunResult,
                         candidate: str | None) -> None:
    session_id = request.get('session_id')
    if candidate is None or not session_id or result.status != 'done':
        return
    output = result.output
    if output is not None and (
        not isinstance(output, dict) or 'report' in output or output.get('kind') not in (None, 'report')
    ):
        return

    owner = request['owner_id']
    try:
        workspace = Workspace(ensure_session_workspace(owner, session_id))
        target = workspace.resolve(candidate)
        if target.suffix.lower() not in _MARKDOWN_SUFFIXES:
            return
        path = target.relative_to(workspace.root).as_posix()
        content, _ = read_session_file(owner, session_id, path)
        report = content.decode('utf-8')
    except (BusinessError, OSError, RuntimeError, ValueError):
        logger.warning('Agent report attachment failed run_id=%s session_id=%s',
                       request['run_id'], session_id, exc_info=True)
        return
    result.output = {**(output or {}), 'kind': 'report', 'report': report, 'report_path': path}


def report_payload(request: dict[str, Any], result: RunResult | None,
                   error: Exception | None = None) -> dict[str, Any]:
    if result is None:
        status = 'failed'
        serialized = None
        usage = {'prompt_tokens': None, 'completion_tokens': None,
                 'tool_calls': None, 'duration_ms': None}
        error_code, error_message = 'worker_execution_error', 'Agent 执行失败，请重试'
    else:
        status = {'done': 'completed', 'failed': 'failed', 'stopped': 'cancelled',
                  'timeout': 'timed_out', 'awaiting_input': 'awaiting_input'}[result.status]
        serialized = {
            'stop_reason': result.stop_reason.value,
            'messages': [message_to_dict(message) for message in result.messages],
            'final_text': result.final_text, 'final_reasoning': result.final_reasoning,
            'output': result.output, 'turns': result.turns, 'duration_ms': result.duration_ms,
            'truncated': result.truncated, 'prompt_tokens': result.prompt_tokens,
            'completion_tokens': result.completion_tokens, 'tool_calls': result.tool_calls,
            'usage_measured': result.usage_measured, 'question': result.question,
            'error': ({'code': result.error.code, 'message': result.error.message}
                      if result.error else None),
        }
        usage = {'prompt_tokens': result.prompt_tokens if result.usage_measured else None,
                 'completion_tokens': result.completion_tokens if result.usage_measured else None,
                 'tool_calls': result.tool_calls, 'duration_ms': result.duration_ms}
        error_code = str(result.error.code) if result.error else None
        error_message = result.error.message if result.error else None
    return {'run_id': request['run_id'], 'task_id': request['task_id'],
            'status': status, 'result': serialized, 'usage': usage,
            'error_code': error_code, 'error_message': error_message}


async def execute_claim(control: AgentControlClient, claim: dict[str, Any], worker_id: str,
                        *, runtime_factory=None) -> None:
    request = claim['run']
    token = int(claim['lease_token'])
    event_seq = int(claim['event_seq'])
    run_id = request['run_id']
    if claim.get('schema_version') != 1 or not claim.get('execution_id'):
        raise BusinessError(20004, 'Agent Worker 只接受 V2 执行任务', 502)
    prefix = '/internal/v2'
    control.execution_id = claim['execution_id']
    stop = asyncio.Event()
    channel = RunChannel()
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
    report_files = ReportFileOperations()
    delivery_error: Exception | None = None
    interruption_error: Exception | None = None

    def on_event(event: AgentEvent) -> None:
        queue.put_nowait(event)
        try:
            report_files.observe(event)
        except Exception:
            logger.warning('Agent report event could not be tracked run_id=%s event_seq=%s',
                           run_id, event.seq, exc_info=True)

    async def publish_events() -> None:
        nonlocal delivery_error
        while (event := await queue.get()) is not None:
            try:
                await control.post(f'{prefix}/runs/{run_id}/events', {
                    'task_id': request['task_id'], 'run_id': run_id,
                    'seq': event_seq + event.seq,
                    'turn': event.turn, 'name': event.name, 'data': event.data,
                    'occurred_at': datetime.now(timezone.utc).isoformat(),
                    'worker_id': worker_id, 'lease_token': token,
                })
            except Exception as exc:  # Delivery failure forbids a success report.
                delivery_error = exc
                stop.set()
            finally:
                queue.task_done()
        queue.task_done()

    async def maintain_lease() -> None:
        nonlocal interruption_error
        failures = 0
        while not stop.is_set():
            await asyncio.sleep(12)
            if stop.is_set():
                return
            try:
                state = await control.heartbeat(run_id, worker_id, token)
            except (httpx.TransportError, httpx.HTTPStatusError, BusinessError) as exc:
                logger.exception('Agent Worker heartbeat failed run_id=%s', run_id)
                failures += 1
                rejected = (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500
                            or isinstance(exc, BusinessError) and exc.status < 500)
                if rejected or failures >= 2:
                    interruption_error = exc
                    stop.set()
                    return
                # Retry once on the next heartbeat. Control still rejects all
                # new calls after the persisted lease actually expires.
                continue
            except Exception as exc:
                logger.exception('Agent Worker heartbeat rejected run_id=%s', run_id)
                interruption_error = exc
                stop.set()
                return
            failures = 0
            if not state.active:
                interruption_error = BusinessError(20004, 'Worker 租约已失效', 409)
                stop.set()
                return
            if state.cancel_requested:
                stop.set()
                return

    async def receive_controls() -> None:
        nonlocal interruption_error
        after_seq = 0
        while not stop.is_set():
            try:
                payload = await control.get(
                    f'{prefix}/runs/{run_id}/controls',
                    params={'worker_id': worker_id, 'lease_token': token,
                            'execution_id': claim['execution_id'], 'after_seq': after_seq},
                )
                if payload.get('cancel_requested'):
                    stop.set()
                    return
                for item in payload.get('controls') or []:
                    after_seq = max(after_seq, int(item['seq']))
                    if item.get('name') == 'steer':
                        channel.steer(str(item.get('text') or ''))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    interruption_error = exc
                    stop.set()
                    return
                logger.warning('Agent control poll failed run_id=%s', run_id, exc_info=True)
            except Exception:
                logger.warning('Agent control poll failed run_id=%s', run_id, exc_info=True)
            await asyncio.sleep(0.5)

    result: RunResult | None = None
    execution_error: Exception | None = None
    from agent_app.execution.metering import WorkerMeter, current_meter
    meter = WorkerMeter(control, run_id=run_id, execution_id=claim['execution_id'],
             worker_id=worker_id, lease_token=token, context=claim['metering_context'], stop=stop,
             risk_profile=claim.get('risk_profile'), dynamic_budget=claim.get('dynamic_model_budget', False))
    meter_token = current_meter.set(meter)
    history = [message_from_dict(item) for item in request.get('history') or []]
    publisher = asyncio.create_task(publish_events())
    heartbeat = asyncio.create_task(maintain_lease())
    controls = asyncio.create_task(receive_controls())
    try:
        if meter is not None and request.get('skills'):
            from agent_app.extensions.skills import default_store
            store = default_store()
            for name in request['skills']:
                await meter.activate(store._require(name), invocation='forced')
        if runtime_factory is None and request.get('model') == 'demo/m1':
            raise RuntimeError('正式 Worker 禁止执行 Mock 任务')
        if request.get('input_ref'):
            raise RuntimeError('Agent Platform input_ref adapter is not configured')
        budget = request.get('budget') or {}
        if budget.get('max_model_tokens') is not None:
            raise RuntimeError('max_model_tokens is not enforceable by the configured Provider')
        runtime = (runtime_factory or build_runtime)(
            owner=request['owner_id'], mode=request.get('mode', 'fast'),
            model=request.get('model'), workspace_id=request.get('workspace_id'),
            session_id=request.get('session_id'), allow_shell=False,
            forced_skills=request.get('skills') or (),
            max_turns=MAX_EXECUTION_TURNS,
            deadline_s=min(run_deadline_s(request.get('mode', 'fast')),
                           float(budget.get('max_duration_s') or run_deadline_s(
                               request.get('mode', 'fast')))),
            max_tool_calls=min(tool_call_budget(request.get('mode', 'fast')),
                               int(budget['max_tool_calls']))
            if budget.get('max_tool_calls') is not None
            else tool_call_budget(request.get('mode', 'fast')),
            tool_budget=min(tool_call_budget(request.get('mode', 'fast')),
                            int(budget['max_tool_calls']))
            if budget.get('max_tool_calls') is not None
            else tool_call_budget(request.get('mode', 'fast')),
        )
        runtime.strict_tool_budget = True
        if meter is not None and not getattr(getattr(runtime, 'provider', runtime), 'supports_call_metering', False):
            stop.set()
            raise BusinessError(20004, 'Provider 未声明调用级门禁能力', 403)
        result = await runtime.run(request['prompt'], run_id=run_id, history=history,
                                   stop=stop, on_event=on_event, channel=channel)
        if meter.failure is not None or interruption_error is not None:
            raise meter.failure or interruption_error
        await queue.join()
        if delivery_error:
            raise RuntimeError('Agent event persistence failed') from delivery_error
        await asyncio.to_thread(attach_report_output, request, result, report_files.latest_path())
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling() or not stop.is_set():
            raise
        # Cancellation can also arrive while activating forced skills, before Runtime starts.
        result = RunResult(stop_reason=StopReason.CANCELLED,
                           messages=[*history, UserMessage(request['prompt'])])
        on_event(AgentEvent(1, 0, 'run_end', {'status': 'stopped', 'stop_reason': 'cancelled'}))
    except Exception as exc:
        execution_error = exc
        result = None
        logger.exception('Agent run failed run_id=%s', run_id)
    finally:
        current_meter.reset(meter_token)
        queue.put_nowait(None)
        await queue.join()
        await publisher
        heartbeat.cancel()
        controls.cancel()
        await asyncio.gather(heartbeat, controls, return_exceptions=True)
    payload = report_payload(request, result, execution_error)
    if isinstance(meter.failure, BusinessError) and meter.failure.status == 403:
        payload['error_code'] = 'authorization_denied'
    payload.update(worker_id=worker_id, lease_token=token)
    try:
        await control.post(f'{prefix}/runs/{run_id}/report', payload)
    except httpx.HTTPStatusError as exc:
        # A stale fencing token is expected to be rejected and must never overwrite a newer run.
        if exc.response.status_code != 409:
            raise


async def run_worker_forever(*, runtime_factory=None) -> None:
    if os.getenv('AGENT_DEMO_MODE') == '1' and runtime_factory is None:
        raise RuntimeError('Mock 环境必须使用 agent_app.demo_worker，禁止启动真实模型 Worker')
    worker_id = os.getenv('AGENT_WORKER_ID', '').strip() or f'{socket.gethostname()}-{os.getpid()}'
    control = AgentControlClient()
    logger.info('Agent Worker started worker_id=%s', worker_id)
    try:
        while True:
            try:
                from agent_app.execution.metering import replay_observation_spool
                await replay_observation_spool(control)
                claim = await control.claim(worker_id)
                if claim.get('run') is None:
                    await asyncio.sleep(1)
                    continue
                if runtime_factory is None:
                    await execute_claim(control, claim, worker_id)
                else:
                    await execute_claim(control, claim, worker_id, runtime_factory=runtime_factory)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Agent Worker polling/execution loop failed')
                await asyncio.sleep(2)
    finally:
        await control.close()

"""Poll durable Agent runs, execute one Runtime attempt, and report through Agent API."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any

import httpx

from agent_app.application.composition import build_runtime
from agent_app.application.policies import run_deadline_s, tool_call_budget
from agent_app.execution.types import (
    AgentEvent, RunChannel, RunResult, message_from_dict, message_to_dict,
)

logger = logging.getLogger('agent.worker')


class AgentControlClient:
    def __init__(self) -> None:
        base = os.getenv('AGENT_INTERNAL_URL', 'http://127.0.0.1:8101').rstrip('/')
        token = os.getenv('AGENT_SERVICE_TOKEN', '').strip()
        if not token:
            raise RuntimeError('AGENT_SERVICE_TOKEN is required by Agent Worker')
        self.client = httpx.AsyncClient(base_url=base, timeout=20,
                                        headers={'Authorization': f'Bearer {token}'})

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.post(path, json=body)
        response.raise_for_status()
        return response.json()

    async def get(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def claim(self, worker_id: str):
        return await self.post('/internal/v1/worker/claim', {'worker_id': worker_id})

    async def close(self) -> None:
        await self.client.aclose()


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


async def execute_claim(control: AgentControlClient, claim: dict[str, Any], worker_id: str) -> None:
    request = claim['run']
    token = int(claim['lease_token'])
    run_id = request['run_id']
    stop = asyncio.Event()
    channel = RunChannel()
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
    delivery_error: Exception | None = None

    async def publish_events() -> None:
        nonlocal delivery_error
        while (event := await queue.get()) is not None:
            try:
                await control.post(f'/internal/v1/runs/{run_id}/events', {
                    'task_id': request['task_id'], 'run_id': run_id, 'seq': event.seq,
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
        while not stop.is_set():
            await asyncio.sleep(12)
            if stop.is_set():
                return
            try:
                state = await control.post(
                    f'/internal/v1/runs/{run_id}/heartbeat',
                    {'worker_id': worker_id, 'lease_token': token},
                )
            except Exception:
                logger.exception('Agent Worker heartbeat failed run_id=%s', run_id)
                stop.set()
                return
            if not state.get('active'):
                stop.set()
                return
            if state.get('cancel_requested'):
                stop.set()

    async def receive_controls() -> None:
        after_seq = 0
        while not stop.is_set():
            try:
                payload = await control.get(
                    f'/internal/v1/runs/{run_id}/controls',
                    params={'owner_id': request['owner_id'], 'after_seq': after_seq},
                )
                for item in payload.get('controls') or []:
                    after_seq = max(after_seq, int(item['seq']))
                    if item.get('name') == 'steer':
                        channel.steer(str(item.get('text') or ''))
            except Exception:
                logger.warning('Agent control poll failed run_id=%s', run_id, exc_info=True)
            await asyncio.sleep(0.5)

    publisher = asyncio.create_task(publish_events())
    heartbeat = asyncio.create_task(maintain_lease())
    controls = asyncio.create_task(receive_controls())
    result: RunResult | None = None
    execution_error: Exception | None = None
    try:
        if request.get('input_ref'):
            raise RuntimeError('Agent Platform input_ref adapter is not configured')
        budget = request.get('budget') or {}
        if budget.get('max_model_tokens') is not None:
            raise RuntimeError('max_model_tokens is not enforceable by the configured Provider')
        runtime = build_runtime(
            owner=request['owner_id'], mode=request.get('mode', 'fast'),
            model=request.get('model'), workspace_id=request.get('workspace_id'),
            session_id=request.get('session_id'), allow_shell=False,
            forced_skills=request.get('skills') or (),
            max_turns=360,
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
        history = [message_from_dict(item) for item in request.get('history') or []]
        result = await runtime.run(request['prompt'], history=history,
                                   stop=stop, on_event=queue.put_nowait, channel=channel)
        await queue.join()
        if delivery_error:
            raise RuntimeError('Agent event persistence failed') from delivery_error
    except Exception as exc:
        execution_error = exc
        result = None
        logger.exception('Agent run failed run_id=%s', run_id)
    finally:
        queue.put_nowait(None)
        await queue.join()
        await publisher
        heartbeat.cancel()
        controls.cancel()
        await asyncio.gather(heartbeat, controls, return_exceptions=True)
    payload = report_payload(request, result, execution_error)
    payload.update(worker_id=worker_id, lease_token=token)
    try:
        await control.post(f'/internal/v1/runs/{run_id}/report', payload)
    except httpx.HTTPStatusError as exc:
        # A stale fencing token is expected to be rejected and must never overwrite a newer run.
        if exc.response.status_code != 409:
            raise


async def run_worker_forever() -> None:
    worker_id = os.getenv('AGENT_WORKER_ID', '').strip() or f'{socket.gethostname()}-{os.getpid()}'
    control = AgentControlClient()
    logger.info('Agent Worker started worker_id=%s', worker_id)
    try:
        while True:
            try:
                claim = await control.claim(worker_id)
                if claim.get('run') is None:
                    await asyncio.sleep(1)
                    continue
                await execute_claim(control, claim, worker_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Agent Worker polling/execution loop failed')
                await asyncio.sleep(2)
    finally:
        await control.close()

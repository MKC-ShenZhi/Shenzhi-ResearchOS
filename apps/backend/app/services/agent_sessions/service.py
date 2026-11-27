"""Project durable Agent Gateway runs into Backend-owned product Sessions and Turns."""
from __future__ import annotations

import asyncio
import logging

from app.core.errors import BusinessError
from app.core.worker_lease import current_worker_id, run_with_heartbeat
from app.services.agent_gateway.client import read_run_update
from app.services.agent_attachments import resolve_agent_attachments
from app.services.agent_sessions.entities import AgentSession, AgentTurn
from app.services.agent_sessions.live import LiveRun, _tasks, append, finish, get_live, invalidate, register
from app.services.agent_sessions.messages import copy_message
from app.services.agent_sessions.repository import agent_session_repository
from app.services.agent_sessions.timeline import TimelineCapture, _closed_transcript
from app.services.agent_uploads import agent_upload_store

logger = logging.getLogger(__name__)


def _definite_submission_rejection(exc: Exception) -> bool:
    """True only when the Agent cannot have received the submission.

    Local authorization/validation rejections never cross the HTTP boundary.
    Remote HTTP errors stay indeterminate: the Agent may have persisted the
    Task before returning an error, so recovery must use the persisted
    idempotency key instead of inventing a terminal result.
    """
    from pydantic import ValidationError

    from app.services.agent_entitlements.service import EntitlementError
    # AgentGateway validates TaskSubmissionWire/TaskSubmissionV2 before its
    # first HTTP request. Such a rejection, like local entitlement gating,
    # cannot leave a Task in Agent even though the Turn is already persisted.
    return isinstance(exc, (EntitlementError, ValidationError))


async def start_session_run(
    *, owner: str, session_id: str, prompt: str, model: str | None, mode: str,
    attachments: list[dict], workspace_id: str | None, skills: list[str],
    allow_shell: bool = True, idempotency_key: str | None = None,
    idempotency_fingerprint: str | None = None, gateway=None,
) -> LiveRun:
    """Validate ownership and concurrency before starting an independent run task."""
    if gateway is None:
        from app.services.agent_gateway.gateway import AgentGateway
        gateway = AgentGateway()
    if idempotency_key is not None:
        existing = await agent_session_repository.find_idempotent_turn(
            session_id, owner, idempotency_key, idempotency_fingerprint or '',
        )
        if existing is not None:
            return await _reuse_turn(existing, owner)

    session = await agent_session_repository.get(session_id, owner)
    runtime_history = list(session.runtime_history)
    attachment_text, warnings, files = await resolve_agent_attachments(attachments, owner)
    # File IDs point to short-lived parsed upload slots. Persist only safe display
    # metadata on this turn; the extracted text is already part of the run transcript.
    display_attachments = []
    for attachment in attachments:
        if attachment.get('kind') == 'file':
            item = files[attachment.get('file_id') or '']
            display_attachments.append({'kind': 'file', 'title': item['filename']})
        else:
            display_attachments.append({
                'kind': attachment.get('kind'),
                'title': attachment.get('title') or attachment.get('ref_id') or '引用条目',
            })
    settings = {
        'model': model, 'mode': mode, 'attachments': display_attachments,
        'workspace_id': workspace_id, 'skills': skills,
        '_agent_owner_id': owner, '_agent_protocol': 2,
    }
    # Keep the normalized request until Agent confirms admission, so a Backend
    # restart can safely resume the same idempotent submission.
    settings['_agent_recovery_request'] = {
        'prompt': prompt + attachment_text,
        'history': runtime_history,
    }
    worker_id = current_worker_id()
    turn, created = await agent_session_repository.start_turn(
        session_id, owner, prompt, settings, warnings,
        worker_id=worker_id,
        idempotency_key=idempotency_key,
        idempotency_fingerprint=idempotency_fingerprint,
    )
    if not created:
        return await _reuse_turn(turn, owner)
    live = LiveRun(session_id=session_id, owner=owner, turn_id=turn.id)
    register(live)
    capture = TimelineCapture(warnings)
    task = None
    try:
        task = await gateway.submit({
            'owner_id': owner, 'prompt': prompt + attachment_text,
            'session_id': session_id, 'turn_id': turn.id,
            'idempotency_key': f'backend-turn:{turn.id}', 'mode': mode,
            'model': model, 'workspace_id': workspace_id, 'skills': skills,
            'history': runtime_history,
        })
        settings.update({'agent_task_id': task['task_id'], 'agent_run_id': task['current_run_id']})
        settings.pop('_agent_recovery_request', None)
        await agent_session_repository.update_turn_settings(
            session_id, owner, turn.id, settings, worker_id=worker_id,
        )
    except Exception as cause:
        if _definite_submission_rejection(cause):
            # A defensive rejection never reached the Agent. Close the product
            # Turn with existing error semantics instead of leaving it running.
            try:
                await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                    'status': 'failed', 'stop_reason': 'error',
                    'error': f'Agent 服务提交失败：{cause}',
                    'warnings': warnings, 'usage': {},
                    'transcript': _closed_transcript(runtime_history, prompt + attachment_text, ''),
                }, worker_id=worker_id)
            finally:
                finish(live)
            raise
        # A remote timeout is not evidence of failure or unused reserve.
        finish(live)
        invalidate(live)
        await agent_session_repository.release_turn_projection(turn.id, worker_id)
        raise

    async def _drive() -> None:
        task_id = task['task_id']
        after_seq = 0
        transcript: list[dict] = []
        try:
            run_id = await _next_task_run(task_id, owner, gateway=gateway)
            await _append_event(live, capture, 'run_start', {'run_id': run_id})
            while True:
                run, events = await read_run_update(gateway, run_id, owner, after_seq)
                for event in events:
                    after_seq = max(after_seq, int(event['seq']))
                    await _append_event(live, capture, event['name'], event['data'])
                next_run_id = (await _next_task_run(task_id, owner, run_id, gateway=gateway)
                               if run.get('report') else None)
                if next_run_id:
                    run_id, after_seq = next_run_id, 0
                    await _append_event(live, capture, 'run_start', {'run_id': run_id})
                    continue
                report = run.get('report')
                if report:
                    result = report.get('result') or {}
                    transcript = result.get('messages') or _closed_transcript(
                        runtime_history, prompt + attachment_text, result.get('final_text', ''),
                    )
                    output = result.get('output') if isinstance(result.get('output'), dict) else {}
                    status = {'completed': 'done', 'failed': 'failed', 'cancelled': 'stopped',
                              'timed_out': 'timeout', 'awaiting_input': 'awaiting_input'}.get(
                                  report.get('status'), 'failed')
                    payload = {
                        'assistant_content': result.get('final_text', ''),
                        'message': capture.messages.result(result, status=status),
                        'reasoning': result.get('final_reasoning', ''),
                        'process': capture.process, 'steers': capture.steers,
                        'report': output.get('report'), 'sources': output.get('sources') or [],
                        'question': result.get('question'), 'warnings': capture.warnings,
                        'error': report.get('error_message'), 'stopped': status in {'stopped', 'timeout'},
                        'stop_reason': result.get('stop_reason') or status, 'status': status,
                        'usage': {key: result.get(key, default) for key, default in (
                            ('prompt_tokens', 0), ('completion_tokens', 0), ('turns', 0),
                            ('duration_ms', 0), ('truncated', False),
                        )},
                        'transcript': transcript,
                    }
                    payload['usage'].update(await gateway.usage(task_id, owner))
                    payload['usage'].update(prompt_tokens=None, completion_tokens=None)
                    await agent_session_repository.finish_turn(
                        session_id, owner, turn.id, payload, worker_id=worker_id,
                    )
                    await _append_event(live, capture, 'result', {
                        'status': status, 'stop_reason': payload['stop_reason'],
                        'final_text': payload['assistant_content'], 'output': output or None,
                        'message': payload['message'],
                        'question': payload['question'], 'turns': payload['usage']['turns'],
                        'duration_ms': payload['usage']['duration_ms'],
                        'prompt_tokens': payload['usage']['prompt_tokens'],
                        'completion_tokens': payload['usage']['completion_tokens'],
                        'truncated': payload['usage']['truncated'],
                        'error': ({'code': report.get('error_code'), 'message': payload['error']}
                                  if payload['error'] else None),
                    })
                    try:
                        await agent_upload_store.consume(owner, list(files))
                    except Exception:
                        logger.exception('Failed to consume Agent attachment text')
                    return
                await asyncio.sleep(0.5)
        except Exception:
            logger.exception('Agent session gateway projection failed: %s', session_id)
            # A failed read is not an execution report. EOF without result lets
            # the client reconnect and recover the still-running product Turn.

    async def _run_with_lease() -> None:
        try:
            if agent_session_repository.is_durable:
                await run_with_heartbeat(
                    _drive, lambda: agent_session_repository.renew_turn(turn.id, worker_id),
                )
            else:
                await _drive()
        finally:
            await _finish_projection(live, worker_id)

    live.task = asyncio.create_task(_run_with_lease())
    _tasks.add(live.task)
    return live


async def _append_event(live: LiveRun, capture: TimelineCapture, name: str, data: dict) -> None:
    capture.event(name, data)
    append(live, name, data)


async def _finish_projection(live: LiveRun, worker_id: str) -> None:
    finish(live)
    _tasks.discard(asyncio.current_task())
    if not live.events or live.events[-1][0] != 'result':
        invalidate(live)
        try:
            await agent_session_repository.release_turn_projection(live.turn_id, worker_id)
        except Exception:
            # If the database is also down, its original lease will expire.
            logger.exception('Failed to release Agent projection lease: %s', live.turn_id)


async def _next_task_run(task_id: str, owner: str, current_run_id: str | None = None, *, gateway=None) -> str | None:
    """Walk the complete attempt order, including retries finished between polls.

    A terminal report and its retry Run are committed atomically by Control.
    Advance only after draining that terminal Run's events, so each sealed prefix
    has the same length (and thus SSE IDs) in live and reconstructed streams.
    """
    if gateway is None:
        from app.services.agent_gateway.gateway import AgentGateway
        gateway = AgentGateway()
    run_ids = await gateway.task_runs(task_id, owner)
    index = run_ids.index(current_run_id) + 1 if current_run_id is not None else 0
    return run_ids[index] if index < len(run_ids) else None


async def _reuse_turn(turn: AgentTurn, owner: str) -> LiveRun:
    """Attach a repeated product request to the existing durable Agent run."""
    live = get_live(turn.session_id, owner)
    if live is not None and live.turn_id == turn.id:
        return live
    if turn.settings.get('_agent_protocol') != 2:
        if turn.status == 'running':
            raise BusinessError(20004, '该 V1 会话运行已退役，无法恢复执行；历史结果仍可查看', 410)
        return _replay_terminal_turn(turn, owner)
    if not turn.settings.get('agent_task_id') and turn.settings.get('_agent_recovery_request'):
        from app.services.agent_gateway.gateway import AgentGateway
        gateway = AgentGateway()
        restored = await gateway.recover_submission(
            turn.settings.get('_agent_owner_id', owner), f'backend-turn:{turn.id}', allow_missing=True)
        if restored is None:
            # Admission never started before the previous Backend stopped.
            # Reuse the persisted Turn and its stable submission key; the V2
            # gateway's database idempotency remains authoritative.
            retry_settings = turn.settings
            recovery = retry_settings.get('_agent_recovery_request')
            if not isinstance(recovery, dict) or not isinstance(recovery.get('prompt'), str) or not isinstance(recovery.get('history'), list):
                raise BusinessError(20004, '该 V2 Turn 缺少安全恢复快照，请重新发送', 409)
            retry_live = LiveRun(session_id=turn.session_id, owner=owner, turn_id=turn.id)
            worker_id = current_worker_id()
            if not await agent_session_repository.claim_turn_projection(
                    turn.session_id, owner, turn.id, worker_id):
                raise BusinessError(20009, '会话投影正在恢复', 409)
            register(retry_live)
            request = {
                'owner_id': retry_settings.get('_agent_owner_id', owner),
                'prompt': recovery['prompt'],
                'session_id': turn.session_id, 'turn_id': turn.id,
                'idempotency_key': f'backend-turn:{turn.id}',
                'mode': retry_settings.get('mode', 'fast'),
                'model': retry_settings.get('model'),
                'workspace_id': retry_settings.get('workspace_id'),
                'skills': retry_settings.get('skills') or [],
                'history': recovery['history'],
            }
            try:
                task = await gateway.submit(request)
                settings = dict(retry_settings, agent_task_id=task['task_id'],
                                agent_run_id=task['current_run_id'])
                settings.pop('_agent_recovery_request', None)
                updated_turn = await agent_session_repository.update_turn_settings(
                    turn.session_id, owner, turn.id, settings, worker_id=worker_id)
                # Release the bootstrap claim before the normal projection
                # acquires its own lease. PostgreSQL does not allow a live
                # lease to be claimed again, even by the same worker.
                await agent_session_repository.release_turn_projection(turn.id, worker_id)
                finish(retry_live)
                invalidate(retry_live)
                recovered = await resume_session_run(
                    turn.session_id, owner, turn_id=updated_turn.id)
                return recovered
            except Exception:
                finish(retry_live)
                invalidate(retry_live)
                await agent_session_repository.release_turn_projection(turn.id, worker_id)
                raise
        worker_id = current_worker_id()
        if not await agent_session_repository.claim_turn_projection(turn.session_id, owner, turn.id, worker_id):
            raise BusinessError(20009, '会话投影正在恢复', 409)
        settings = dict(turn.settings, agent_task_id=restored['task_id'], agent_run_id=restored['current_run_id'])
        settings.pop('_agent_recovery_request', None)
        await agent_session_repository.update_turn_settings(turn.session_id, owner, turn.id, settings, worker_id=worker_id)
        await agent_session_repository.release_turn_projection(turn.id, worker_id)
        turn.settings = settings
    task_id = turn.settings.get('agent_task_id')
    run_id = turn.settings.get('agent_run_id')
    if task_id and run_id:
        return await resume_session_run(turn.session_id, owner, turn_id=turn.id)
    if turn.status == 'running':
        raise BusinessError(20009, '会话运行尚未关联 Agent Task，请稍后重试', 409)

    # Imported legacy turns predate Agent Task IDs. Reconstruct their final product
    # stream from the persisted projection so idempotent retries remain replayable.
    return _replay_terminal_turn(turn, owner)


def _replay_terminal_turn(turn: AgentTurn, owner: str) -> LiveRun:
    """Build a client stream from the persisted product projection only."""
    live = LiveRun(session_id=turn.session_id, owner=owner, turn_id=turn.id)
    # An old idempotency key must not replace the latest Session subscription.
    run_id = str(turn.settings.get('agent_run_id') or turn.id)
    append(live, 'run_start', {'run_id': run_id})
    for item in turn.process:
        if item.get('kind') == 'text':
            append(live, 'delta', {'turn': 0, 'text': item.get('text', '')})
        elif item.get('kind') == 'reasoning':
            append(live, 'delta', {'turn': 0, 'reasoning': item.get('text', '')})
        elif item.get('kind') == 'tool':
            tool = item.get('tool') or {}
            append(live, 'tool_call', {
                'tool_call_id': tool.get('toolCallId', ''), 'name': tool.get('name', ''),
                'arguments': tool.get('arguments', ''),
            })
            if tool.get('done'):
                append(live, 'tool_end', {
                    'tool_call_id': tool.get('toolCallId', ''),
                    'is_error': tool.get('isError', False),
                    'cancelled': tool.get('cancelled', False),
                    'duration_ms': tool.get('durationMs', 0),
                    'summary': tool.get('summary', ''),
                })
    if turn.warnings:
        append(live, 'meta', {'warnings': turn.warnings})
    append(live, 'result', {
        'status': turn.status, 'stop_reason': turn.stop_reason or turn.status,
        'final_text': turn.assistant_content,
        'message': copy_message(turn.message, status=turn.status),
        'output': ({'report': turn.report, 'sources': turn.sources}
                   if turn.report or turn.sources else None),
        'question': turn.question, **(turn.usage or {}),
        'error': ({'code': 20004, 'message': turn.error} if turn.error else None),
    })
    finish(live)
    return live


async def resume_session_run(session_id: str, owner: str, *, turn_id: str | None = None) -> LiveRun:
    """Replay durable Agent events, or rebuild an active Session projection."""
    session = await agent_session_repository.get(session_id, owner)
    turn = next((item for item in reversed(session.turns)
                 if turn_id is None or item.id == turn_id), None)
    if turn is None:
        raise BusinessError(20004, '当前没有可回放的 Agent 运行', 404)
    if turn.settings.get('_agent_protocol') != 2:
        if turn.status == 'running':
            raise BusinessError(20004, '该 V1 会话运行已退役，无法恢复执行；历史结果仍可查看', 410)
        return _replay_terminal_turn(turn, owner)
    if not (turn.settings.get('agent_task_id') and turn.settings.get('agent_run_id')):
        return await _reuse_turn(turn, owner)
    from app.services.agent_gateway.gateway import AgentGateway
    gateway = AgentGateway()
    task_id = turn.settings.get('agent_task_id')
    worker_id = current_worker_id()
    execution_owner = turn.settings.get('_agent_owner_id', owner)
    active_turn = turn.status == 'running'
    if active_turn and not await agent_session_repository.claim_turn_projection(
            session_id, owner, turn.id, worker_id):
        raise BusinessError(20009, '会话投影正在其他 Backend 实例恢复', 409)

    live = LiveRun(session_id=session_id, owner=owner, turn_id=turn.id)
    if turn.id == session.turns[-1].id:
        register(live)
    capture = TimelineCapture(turn.warnings)
    turn_index = next(index for index, item in enumerate(session.turns) if item.id == turn.id)
    history = session.turns[turn_index - 1].transcript if turn_index else []

    async def drive() -> None:
        after_seq = 0
        try:
            current_run = await _next_task_run(task_id, execution_owner, gateway=gateway)
            append(live, 'run_start', {'run_id': current_run})
            while True:
                run, events = await read_run_update(gateway, current_run, execution_owner, after_seq)
                for event in events:
                    after_seq = max(after_seq, int(event['seq']))
                    await _append_event(live, capture, event['name'], event['data'])
                next_run_id = (await _next_task_run(task_id, execution_owner, current_run, gateway=gateway)
                               if run.get('report') else None)
                if next_run_id:
                    current_run, after_seq = next_run_id, 0
                    await _append_event(live, capture, 'run_start', {'run_id': current_run})
                    continue
                report = run.get('report')
                if report:
                    result = report.get('result') or {}
                    output = result.get('output') if isinstance(result.get('output'), dict) else {}
                    status = {'completed': 'done', 'failed': 'failed', 'cancelled': 'stopped',
                              'timed_out': 'timeout', 'awaiting_input': 'awaiting_input'}.get(
                                  report.get('status'), 'failed')
                    usage = {key: result.get(key, default) for key, default in (
                        ('prompt_tokens', 0), ('completion_tokens', 0), ('turns', 0),
                        ('duration_ms', 0), ('truncated', False),
                    )}
                    usage.update(await gateway.usage(task_id, execution_owner))
                    usage.update(prompt_tokens=None, completion_tokens=None)
                    final_text = result.get('final_text', '')
                    message = capture.messages.result(result, status=status)
                    if active_turn:
                        await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                            'assistant_content': final_text,
                            'message': message,
                            'reasoning': result.get('final_reasoning', ''),
                            'process': capture.process, 'steers': capture.steers,
                            'report': output.get('report'), 'sources': output.get('sources') or [],
                            'question': result.get('question'), 'warnings': capture.warnings,
                            'error': report.get('error_message'),
                            'stopped': status in {'stopped', 'timeout'},
                            'stop_reason': result.get('stop_reason') or status, 'status': status,
                            'usage': usage,
                            'transcript': result.get('messages') or _closed_transcript(
                                history, turn.user_content, final_text),
                        }, worker_id=worker_id)
                    await _append_event(live, capture, 'result', {
                        'status': status, 'stop_reason': result.get('stop_reason') or status,
                        'final_text': final_text, 'output': output or None,
                        'message': message,
                        'question': result.get('question'), **usage,
                        'error': ({'code': report.get('error_code'),
                                   'message': report.get('error_message')}
                                  if report.get('error_code') else None),
                    })
                    return
                await asyncio.sleep(0.5)
        except Exception:
            logger.exception('Agent session recovery projection failed: %s', session_id)

    async def run_projection() -> None:
        try:
            if active_turn and agent_session_repository.is_durable:
                await run_with_heartbeat(
                    drive, lambda: agent_session_repository.renew_turn(turn.id, worker_id),
                )
            else:
                await drive()
        finally:
            await _finish_projection(live, worker_id)

    live.task = asyncio.create_task(run_projection())
    _tasks.add(live.task)
    return live

async def get_session_detail(session_id: str, owner: str) -> AgentSession:
    """Reconcile process-local orphan turns before returning session detail."""
    session = await agent_session_repository.get(session_id, owner)
    if (get_live(session_id, owner) is not None
            or agent_session_repository.is_durable):
        # A missing local LiveRun does not prove a durable turn's lease expired;
        # the repository reconciles expired leases while loading the session.
        return session
    history: list[dict] = []
    reconciled = False
    for turn in session.turns:
        if (turn.status == 'running'
                and (turn.settings.get('_agent_protocol') != 2
                     or (not turn.settings.get('agent_task_id')
                         and not turn.settings.get('_agent_recovery_request')))):
            payload = {
                'status': 'stopped', 'stop_reason': 'interrupted', 'stopped': True,
                'error': '运行已中断（服务重启或异常退出），请重新发送',
                'transcript': _closed_transcript(history, turn.user_content, turn.assistant_content),
            }
            try:
                await agent_session_repository.finish_turn(session_id, owner, turn.id, payload)
            except Exception:
                # A concurrent detail request may have already reconciled this snapshot.
                current = await agent_session_repository.get(session_id, owner)
                if any(item.id == turn.id and item.status == 'running' for item in current.turns):
                    raise
            history = payload['transcript']
            reconciled = True
        else:
            history = turn.transcript
    return await agent_session_repository.get(session_id, owner) if reconciled else session

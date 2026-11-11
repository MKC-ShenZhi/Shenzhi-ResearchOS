"""Project durable Agent Gateway runs into Backend-owned product Sessions and Turns."""
from __future__ import annotations

import asyncio
import logging

from app.core.errors import BusinessError
from app.core.worker_lease import current_worker_id, run_with_heartbeat
from app.services.agent_gateway.client import agent_gateway
from app.services.agent_attachments import resolve_agent_attachments
from app.services.agent_sessions.entities import AgentSession, AgentTurn
from app.services.agent_sessions.live import LiveRun, _tasks, append, finish, get_live, register
from app.services.agent_sessions.repository import agent_session_repository
from app.services.agent_sessions.timeline import TimelineCapture, _closed_transcript
from app.services.agent_uploads import agent_upload_store

logger = logging.getLogger(__name__)


async def start_session_run(
    *, owner: str, session_id: str, prompt: str, model: str | None, mode: str,
    attachments: list[dict], workspace_id: str | None, skills: list[str],
    allow_shell: bool = True, idempotency_key: str | None = None,
    idempotency_fingerprint: str | None = None,
) -> LiveRun:
    """Validate ownership and concurrency before starting an independent run task."""
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
        task = await agent_gateway.submit({
            'owner_id': owner, 'prompt': prompt + attachment_text,
            'session_id': session_id, 'turn_id': turn.id,
            'idempotency_key': f'backend-turn:{turn.id}', 'mode': mode,
            'model': model, 'workspace_id': workspace_id, 'skills': skills,
            'history': runtime_history,
        })
        settings.update({'agent_task_id': task['task_id'], 'agent_run_id': task['current_run_id']})
        await agent_session_repository.update_turn_settings(
            session_id, owner, turn.id, settings, worker_id=worker_id,
        )
    except Exception as cause:
        if task is not None:
            try:
                await agent_gateway.cancel(task['task_id'], owner)
            except Exception:
                logger.exception('Failed to cancel unlinked Agent task: %s', task.get('task_id'))
        error = f'Agent 服务提交失败：{cause}'
        try:
            await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                'status': 'failed', 'stop_reason': 'error', 'error': error,
                'warnings': warnings, 'usage': {},
                'transcript': _closed_transcript(runtime_history, prompt + attachment_text, ''),
            }, worker_id=worker_id)
        finally:
            finish(live)
        raise

    async def _drive() -> None:
        task_id = task['task_id']
        run_id = task['current_run_id']
        after_seq = 0
        transcript: list[dict] = []
        await _append_event(live, capture, 'run_start', {'run_id': run_id})
        try:
            while True:
                events = await agent_gateway.events(run_id, owner, after_seq)
                for event in events:
                    after_seq = max(after_seq, int(event['seq']))
                    await _append_event(live, capture, event['name'], event['data'])
                run = await agent_gateway.run(run_id, owner)
                task_state = await agent_gateway.task(task_id, owner)
                next_run_id = task_state.get('current_run_id')
                if run.get('report') and next_run_id and next_run_id != run_id:
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
                    await agent_session_repository.finish_turn(
                        session_id, owner, turn.id, payload, worker_id=worker_id,
                    )
                    await _append_event(live, capture, 'result', {
                        'status': status, 'stop_reason': payload['stop_reason'],
                        'final_text': payload['assistant_content'], 'output': output or None,
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
        except Exception as cause:
            logger.exception('Agent session gateway projection failed: %s', session_id)
            partial = ''.join(str(item.get('text') or '') for item in capture.process
                              if item.get('kind') == 'text')
            await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                'assistant_content': partial, 'process': capture.process,
                'steers': capture.steers, 'warnings': capture.warnings,
                'error': f'Agent 运行状态同步失败：{cause}', 'stopped': False,
                'stop_reason': 'error', 'status': 'failed', 'usage': {},
                'transcript': _closed_transcript(runtime_history, prompt + attachment_text, partial),
            }, worker_id=worker_id)
            await _append_event(live, capture, 'result', {
                'status': 'failed', 'stop_reason': 'error', 'final_text': partial,
                'output': None, 'question': None, 'turns': 0, 'duration_ms': 0,
                'prompt_tokens': 0, 'completion_tokens': 0, 'truncated': False,
                'error': {'code': 20004, 'message': 'Agent 运行状态同步失败'},
            })

    async def _run_with_lease() -> None:
        try:
            if agent_session_repository.is_durable:
                await run_with_heartbeat(
                    _drive, lambda: agent_session_repository.renew_turn(turn.id, worker_id),
                )
            else:
                await _drive()
        finally:
            finish(live)
            _tasks.discard(asyncio.current_task())

    live.task = asyncio.create_task(_run_with_lease())
    _tasks.add(live.task)
    return live


async def _append_event(live: LiveRun, capture: TimelineCapture, name: str, data: dict) -> None:
    capture.event(name, data)
    append(live, name, data)


async def _reuse_turn(turn: AgentTurn, owner: str) -> LiveRun:
    """Attach a repeated product request to the existing durable Agent run."""
    live = get_live(turn.session_id, owner)
    if live is not None:
        return live
    task_id = turn.settings.get('agent_task_id')
    run_id = turn.settings.get('agent_run_id')
    if task_id and run_id:
        return await resume_session_run(turn.session_id, owner)
    if turn.status == 'running':
        raise BusinessError(20009, '会话运行尚未关联 Agent Task，请稍后重试', 409)

    # Imported legacy turns predate Agent Task IDs. Reconstruct their final product
    # stream from the persisted projection so idempotent retries remain replayable.
    live = LiveRun(session_id=turn.session_id, owner=owner, turn_id=turn.id)
    register(live)
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
                    'duration_ms': tool.get('durationMs', 0),
                    'summary': tool.get('summary', ''),
                })
    if turn.warnings:
        append(live, 'meta', {'warnings': turn.warnings})
    append(live, 'result', {
        'status': turn.status, 'stop_reason': turn.stop_reason or turn.status,
        'final_text': turn.assistant_content,
        'output': ({'report': turn.report, 'sources': turn.sources}
                   if turn.report or turn.sources else None),
        'question': turn.question, **(turn.usage or {}),
        'error': ({'code': 20004, 'message': turn.error} if turn.error else None),
    })
    finish(live)
    return live


async def resume_session_run(session_id: str, owner: str) -> LiveRun:
    """Replay durable Agent events, or rebuild an active Session projection."""
    session = await agent_session_repository.get(session_id, owner)
    turn = next((item for item in reversed(session.turns)
                 if item.settings.get('agent_task_id') and item.settings.get('agent_run_id')), None)
    if turn is None:
        raise BusinessError(20004, '当前没有可回放的 Agent 运行', 404)
    task_id = turn.settings.get('agent_task_id')
    run_id = turn.settings.get('agent_run_id')
    worker_id = current_worker_id()
    active_turn = turn.status == 'running'
    if active_turn and not await agent_session_repository.claim_turn_projection(
            session_id, owner, turn.id, worker_id):
        raise BusinessError(20009, '会话投影正在其他 Backend 实例恢复', 409)

    live = LiveRun(session_id=session_id, owner=owner, turn_id=turn.id)
    register(live)
    capture = TimelineCapture(turn.warnings)
    history = session.turns[-2].transcript if len(session.turns) > 1 else []

    async def drive() -> None:
        current_run = run_id
        after_seq = 0
        append(live, 'run_start', {'run_id': current_run})
        try:
            while True:
                for event in await agent_gateway.events(current_run, owner, after_seq):
                    after_seq = max(after_seq, int(event['seq']))
                    await _append_event(live, capture, event['name'], event['data'])
                run = await agent_gateway.run(current_run, owner)
                task_state = await agent_gateway.task(task_id, owner)
                latest = task_state.get('current_run_id')
                if run.get('report') and latest and latest != current_run:
                    current_run, after_seq = latest, 0
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
                    final_text = result.get('final_text', '')
                    if active_turn:
                        await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                            'assistant_content': final_text,
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
                        'question': result.get('question'), **usage,
                        'error': ({'code': report.get('error_code'),
                                   'message': report.get('error_message')}
                                  if report.get('error_code') else None),
                    })
                    return
                await asyncio.sleep(0.5)
        except Exception as cause:
            logger.exception('Agent session recovery projection failed: %s', session_id)
            partial = ''.join(str(item.get('text') or '') for item in capture.process
                              if item.get('kind') == 'text')
            if active_turn:
                try:
                    await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                        'assistant_content': partial, 'process': capture.process,
                        'steers': capture.steers, 'warnings': capture.warnings,
                        'error': f'Agent 运行状态恢复失败：{cause}', 'stopped': False,
                        'stop_reason': 'error', 'status': 'failed', 'usage': {},
                        'transcript': _closed_transcript(history, turn.user_content, partial),
                    }, worker_id=worker_id)
                except Exception:
                    logger.exception('Failed to close recovered Agent turn: %s', turn.id)
            append(live, 'result', {
                'status': 'failed', 'stop_reason': 'error', 'final_text': partial,
                'output': None, 'question': None, 'turns': 0, 'duration_ms': 0,
                'prompt_tokens': 0, 'completion_tokens': 0, 'truncated': False,
                'error': {'code': 20004, 'message': 'Agent 运行状态恢复失败'},
            })

    async def run_projection() -> None:
        try:
            if active_turn and agent_session_repository.is_durable:
                await run_with_heartbeat(
                    drive, lambda: agent_session_repository.renew_turn(turn.id, worker_id),
                )
            else:
                await drive()
        finally:
            finish(live)
            _tasks.discard(asyncio.current_task())

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
        if turn.status == 'running':
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

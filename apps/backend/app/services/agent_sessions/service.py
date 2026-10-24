"""Application service joining persistent Agent sessions to the existing runtime."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.agent import service as agent_runtime
from app.services.agent.types import RunResult, message_to_dict
from app.services.agent_sessions.entities import AgentSession
from app.services.agent_sessions.live import LiveRun, _tasks, append, finish, get_live, register
from app.services.agent_sessions.repository import agent_session_repository
from app.services.agent_uploads import agent_upload_store

logger = logging.getLogger(__name__)

class TimelineCapture:
    """Capture the same interleaved timeline that the Web UI renders during SSE."""

    def __init__(self, warnings: list[str]):
        self.process: list[dict[str, Any]] = []
        self.steers: list[dict[str, str]] = []
        self.warnings = list(warnings)
        self.turn = -1
        self.reasoning_index = -1
        self.text_index = -1

    def event(self, name: str, data: dict[str, Any]) -> None:
        turn = int(data.get('turn') or 0)
        if name == 'delta':
            if turn != self.turn:
                self.turn = turn
                self.reasoning_index = -1
                self.text_index = -1
            reasoning = str(data.get('reasoning') or '')
            text = str(data.get('text') or '')
            if reasoning:
                self.reasoning_index = self._append_text('reasoning', reasoning, self.reasoning_index)
            if text:
                self.text_index = self._append_text('text', text, self.text_index)
        elif name == 'tool_call':
            self.process.append({'kind': 'tool', 'tool': {
                'toolCallId': str(data.get('tool_call_id') or ''),
                'name': str(data.get('name') or ''),
                'arguments': str(data.get('arguments') or ''),
                'done': False, 'isError': False, 'durationMs': 0,
            }})
        elif name == 'tool_end':
            call_id = str(data.get('tool_call_id') or '')
            for item in reversed(self.process):
                if item.get('kind') == 'tool' and item.get('tool', {}).get('toolCallId') == call_id:
                    item['tool'].update({
                        'done': True,
                        'isError': bool(data.get('is_error')),
                        'durationMs': int(data.get('duration_ms') or 0),
                        'summary': str(data.get('summary') or ''),
                    })
                    break
        elif name == 'message':
            kind = str(data.get('kind') or 'steer')
            if kind == 'system':
                return
            if kind not in {'steer', 'follow_up'}:
                kind = 'steer'
            self.steers.append({'text': str(data.get('text') or ''), 'kind': kind})
        elif name == 'meta' and isinstance(data.get('warnings'), list):
            self.warnings = [str(item) for item in data['warnings']]

    def _append_text(self, kind: str, chunk: str, index: int) -> int:
        if index >= 0 and index < len(self.process) and self.process[index].get('kind') == kind:
            self.process[index]['text'] = str(self.process[index].get('text') or '') + chunk
            return index
        self.process.append({'kind': kind, 'text': chunk})
        return len(self.process) - 1


async def start_session_run(
    *, owner: str, session_id: str, prompt: str, model: str | None, mode: str,
    attachments: list[dict], workspace_id: str | None, skills: list[str],
    allow_shell: bool = True,
) -> LiveRun:
    """Validate ownership and concurrency before starting an independent run task."""
    session = await agent_session_repository.get(session_id, owner)
    runtime_history = list(session.runtime_history)
    history = agent_runtime.decode_history(runtime_history)
    attachment_text, warnings, files = await agent_runtime.resolve_attachments(attachments, owner)
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
    runtime = agent_runtime.build_run_runtime(
        owner=owner, model=model, mode=mode, workspace_id=workspace_id,
        forced_skills=skills, session_id=session_id, allow_shell=allow_shell,
    )
    turn = await agent_session_repository.start_turn(
        session_id, owner, prompt, settings, warnings,
    )
    live = LiveRun(session_id=session_id, owner=owner, turn_id=turn.id)
    register(live)
    capture = TimelineCapture(warnings)

    async def complete(result: RunResult) -> None:
        output = result.output if isinstance(result.output, dict) else {}
        sources = output.get('sources') if isinstance(output.get('sources'), list) else []
        await agent_session_repository.finish_turn(session_id, owner, turn.id, {
            'assistant_content': result.final_text,
            'reasoning': result.final_reasoning,
            'process': capture.process,
            'steers': capture.steers,
            'report': output.get('report') if isinstance(output.get('report'), str) else None,
            'sources': sources,
            'question': result.question,
            'warnings': capture.warnings,
            'error': result.error.message if result.error else None,
            'stopped': result.status in {'stopped', 'timeout'},
            'stop_reason': result.stop_reason.value,
            'status': result.status,
            'usage': {
                'prompt_tokens': result.prompt_tokens,
                'completion_tokens': result.completion_tokens,
                'turns': result.turns,
                'duration_ms': result.duration_ms,
                'truncated': result.truncated,
            },
            'transcript': [message_to_dict(message) for message in result.messages],
        })
        try:
            await agent_upload_store.consume(owner, list(files))
        except Exception:
            logger.exception('Failed to delete consumed Agent attachment text')

    async def _drive() -> None:
        try:
            async for name, data in agent_runtime.run_events(
                runtime, prompt + attachment_text, history,
                meta={'warnings': warnings} if warnings else None,
                owner=owner, session_id=session_id, on_complete=complete,
            ):
                capture.event(name, data)
                append(live, name, data)
        except Exception as cause:
            logger.exception('Agent session run failed: %s', session_id)
            error = f'Agent 运行失败：{cause}'
            partial = ''.join(
                str(item.get('text') or '') for item in capture.process
                if item.get('kind') == 'text')
            try:
                await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                    'assistant_content': partial,
                    'process': capture.process,
                    'steers': capture.steers,
                    'warnings': capture.warnings,
                    'error': error,
                    'stopped': False,
                    'stop_reason': 'error',
                    'status': 'failed',
                    'usage': {},
                    # Tool calls may be incomplete after a bridge failure. Keep the
                    # observed timeline but close the model-facing transcript.
                    'transcript': _closed_transcript(runtime_history, turn.user_content, partial),
                })
                await agent_upload_store.consume(owner, list(files))
            except Exception:
                logger.exception('Failed to persist interrupted Agent session run')
            append(live, 'result', {
                'status': 'failed', 'stop_reason': 'error', 'final_text': partial,
                'output': None, 'question': None, 'turns': 0, 'duration_ms': 0,
                'prompt_tokens': 0, 'completion_tokens': 0, 'truncated': False,
                'error': {'code': 20004, 'message': error},
            })
        finally:
            finish(live)
            _tasks.discard(asyncio.current_task())

    live.task = asyncio.create_task(_drive())
    _tasks.add(live.task)
    return live


def _closed_transcript(history: list[dict], user_content: str, partial: str) -> list[dict]:
    return [*history,
            {'kind': 'user', 'text': user_content},
            {'kind': 'assistant', 'content': partial, 'reasoning': '',
             'tool_calls': [], 'stop_reason': 'cancelled', 'usage_tokens': 0}]


async def get_session_detail(session_id: str, owner: str) -> AgentSession:
    """Close orphan turns left by a previous process before returning a session."""
    session = await agent_session_repository.get(session_id, owner)
    if get_live(session_id, owner) is not None:
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

"""Application service joining persistent Agent sessions to the existing runtime."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.services.agent import service as agent_runtime
from app.services.agent.types import RunResult, message_to_dict
from app.services.agent_sessions.repository import agent_session_repository


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
            if kind not in {'steer', 'follow_up', 'system'}:
                kind = 'steer'
            self.steers.append({'text': str(data.get('text') or ''), 'kind': kind})
        elif name == 'compaction':
            self.steers.append({
                'kind': 'system',
                'text': f"上下文已压缩（{data.get('before_chars', 0)} → {data.get('after_chars', 0)} 字符）",
            })
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
) -> AsyncIterator[tuple[str, dict]]:
    """Validate ownership and concurrency before returning the live SSE iterator."""
    session = await agent_session_repository.get(session_id, owner)
    history = agent_runtime.decode_history(session.runtime_history)
    attachment_text, warnings = agent_runtime.resolve_attachments(attachments, owner)
    settings = {
        'model': model, 'mode': mode, 'attachments': attachments,
        'workspace_id': workspace_id, 'skills': skills,
    }
    runtime = agent_runtime.build_run_runtime(
        owner=owner, model=model, mode=mode, workspace_id=workspace_id,
        forced_skills=skills, session_id=session_id,
    )
    turn = await agent_session_repository.start_turn(
        session_id, owner, prompt, settings, warnings,
    )
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

    async def events() -> AsyncIterator[tuple[str, dict]]:
        completed = False
        try:
            async for name, data in agent_runtime.run_events(
                runtime, prompt + attachment_text, history,
                meta={'warnings': warnings} if warnings else None,
                owner=owner, session_id=session_id, on_complete=complete,
            ):
                capture.event(name, data)
                if name == 'result':
                    completed = True
                yield name, data
        finally:
            # run_events persists on disconnect through its worker callback. This fallback only
            # covers setup/bridge failures that occurred before a RunResult could be produced.
            if not completed and turn.status == 'running':
                # The repository entity is a snapshot; a duplicate completion is rejected and ignored.
                try:
                    partial = ''.join(
                        str(item.get('text') or '') for item in capture.process
                        if item.get('kind') == 'text')
                    await agent_session_repository.finish_turn(session_id, owner, turn.id, {
                        'assistant_content': partial,
                        'process': capture.process,
                        'steers': capture.steers,
                        'warnings': capture.warnings,
                        'error': 'SSE connection ended before the run completed',
                        'stopped': True,
                        'stop_reason': 'connection_closed',
                        'status': 'stopped',
                        'usage': {},
                        # Do not persist incomplete tool calls: the next provider request requires a
                        # closed transcript. The UI timeline still retains every observed tool event.
                        'transcript': [*session.runtime_history,
                                       {'kind': 'user', 'text': prompt},
                                       {'kind': 'assistant', 'content': partial, 'reasoning': '',
                                        'tool_calls': [], 'stop_reason': 'cancelled',
                                        'usage_tokens': 0}],
                    })
                except Exception:
                    pass

    return events()

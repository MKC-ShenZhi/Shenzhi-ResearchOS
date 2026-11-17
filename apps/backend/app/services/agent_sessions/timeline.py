"""Translate runtime events into the persisted product timeline."""
from __future__ import annotations

from typing import Any


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


def _closed_transcript(history: list[dict], user_content: str, partial: str) -> list[dict]:
    return [*history,
            {'kind': 'user', 'text': user_content},
            {'kind': 'assistant', 'content': partial, 'reasoning': '',
             'tool_calls': [], 'stop_reason': 'cancelled', 'usage_tokens': 0}]

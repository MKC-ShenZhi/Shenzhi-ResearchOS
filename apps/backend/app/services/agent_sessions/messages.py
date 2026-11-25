"""Validate Agent-owned message snapshots without normalizing their JSON payload.

Backend stores and forwards the snapshot, rather than rebuilding blocks from
legacy text events. The shared contract owns block types and reference rules.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent_contracts.messages import AIMessage, MESSAGE_EVENT_MODELS

from app.core.errors import BusinessError


def copy_message(value: dict[str, Any] | None, *, status: str | None = None) -> dict[str, Any] | None:
    if value is None:
        return None
    message = AIMessage.model_validate(value)
    if status is not None and message.status != status:
        raise BusinessError(20004, 'Agent 消息状态与运行终态不一致', 502)
    # model_dump would add defaults/remove explicit nulls depending on options.
    # Preserve original keys, Markdown whitespace, array order and all metadata.
    return deepcopy(value)


def result_message(result: dict, *, status: str,
                   event_message: dict | None = None) -> dict | None:
    message = copy_message(result.get('message'), status=status)
    terminal = copy_message(event_message, status=status)
    if message is not None and terminal is not None and message != terminal:
        raise BusinessError(20004, 'Agent 消息报告与 message_end 不一致', 502)
    return message if message is not None else terminal


class MessageCapture:
    """Observe final snapshots without rebuilding blocks or retaining token events."""

    def __init__(self) -> None:
        self.message: dict | None = None
        self.seen = False

    def event(self, name: str, data: dict) -> bool:
        if name == 'run_start':
            self.message = None
            self.seen = False
        model = MESSAGE_EVENT_MODELS.get(name)
        if model is None:
            return False
        model.model_validate(data)
        self.seen = True
        if name == 'message_start':
            self.message = None
        elif name == 'message_end':
            self.message = copy_message(data['message'])
        return True

    def result(self, result: dict, *, status: str) -> dict | None:
        message = result_message(result, status=status, event_message=self.message)
        if message is None and self.seen:
            raise BusinessError(20004, 'Agent 结构化消息缺少最终快照', 502)
        return message

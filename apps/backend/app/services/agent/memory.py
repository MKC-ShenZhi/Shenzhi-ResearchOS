"""Agent 内部记忆与断点：turn 边界 Checkpoint 与可插拔存储。

职责边界（与平台业务分层）：
- 用户可见的会话历史归平台业务层（chat sessions）；Agent 内部的记忆只有两样——
  上下文装配策略（context.py 的轮组预算）与这里的 Checkpoint（恢复/审计用）；
- 跨 run 的记忆由调用方经 history 参数回传，基座不持有。
Checkpoint 只在 turn 边界写（半途 turn 永不入库），因此任何时刻加载的快照
都是消息合法、可继续执行的 transcript。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Protocol

from app.services.agent.types import AgentMessage, message_from_dict


@dataclass
class Checkpoint:
    run_id: str
    turn: int
    messages: list[dict]  # message_to_dict 编码；恢复时经 message_from_dict 解码
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # compaction 后有效：最新摘要 + 已压缩掉的文件操作清单（pi CompactionEntry 同款持久化要点）。
    # resume 时恢复进 _RunState，保证下一次 compaction 能对已有摘要做迭代更新。
    summary: str = ''
    read_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    # run 级状态：resume 后不重置（预算/已装载技能/文件清单延续）
    loaded_skills: list[str] = field(default_factory=list)
    pinned_chars: int = 0
    executed_tools: int = 0
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({
            'run_id': self.run_id, 'turn': self.turn, 'messages': self.messages,
            'prompt_tokens': self.prompt_tokens, 'completion_tokens': self.completion_tokens,
            'summary': self.summary, 'read_files': self.read_files,
            'modified_files': self.modified_files, 'loaded_skills': self.loaded_skills,
            'pinned_chars': self.pinned_chars, 'executed_tools': self.executed_tools,
            'created_at': self.created_at,
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> 'Checkpoint':
        data = json.loads(raw)
        return cls(run_id=str(data['run_id']), turn=int(data['turn']),
                   messages=list(data['messages']),
                   prompt_tokens=int(data.get('prompt_tokens', 0)),
                   completion_tokens=int(data.get('completion_tokens', 0)),
                   summary=str(data.get('summary', '')),
                   read_files=list(data.get('read_files', [])),
                   modified_files=list(data.get('modified_files', [])),
                   loaded_skills=list(data.get('loaded_skills', [])),
                   pinned_chars=int(data.get('pinned_chars', 0)),
                   executed_tools=int(data.get('executed_tools', 0)),
                   created_at=float(data.get('created_at', time.time())))

    def decoded_messages(self) -> list[AgentMessage]:
        return [message_from_dict(item) for item in self.messages]


class CheckpointStore(Protocol):
    async def save(self, checkpoint: Checkpoint) -> None: ...
    async def load(self, run_id: str) -> Checkpoint | None: ...


class InMemoryCheckpointStore:
    """进程内实现；持久化实现（Postgres JSONB 等）由业务层按同一 Protocol 提供。"""

    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}

    async def save(self, checkpoint: Checkpoint) -> None:
        self._checkpoints[checkpoint.run_id] = checkpoint

    async def load(self, run_id: str) -> Checkpoint | None:
        return self._checkpoints.get(run_id)

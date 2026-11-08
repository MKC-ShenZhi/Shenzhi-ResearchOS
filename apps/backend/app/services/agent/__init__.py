"""Agent 基座兼容公共出口；新应用组装应使用 app.services.agent.app.composition。

这里保留旧 AgentRuntime 的默认 Provider 行为和常用类型导出，避免迁移破坏既有调用方。
纯执行代码直接从 execution 子包导入；能力、扩展与应用装配从各自子包导入。
"""
from app.services.agent.execution.memory import Checkpoint, CheckpointStore
from app.services.agent.provider import (
    Finish, ModelProvider, ModelRequest, OpenAICompatProvider, ReasoningDelta, TextDelta, ToolCallEvent, Usage,
)
from app.services.agent.runtime import AgentRuntime
from app.services.agent.extensions.skills import Skill, SkillRoot, SkillStore, default_store
from app.services.agent.execution.tools import (
    AfterToolCall, BeforeToolCall, Tool, ToolPolicy, ToolRegistry, ToolSpec, ToolOutput, tool,
)
from app.services.agent.execution.types import (
    AgentEvent, AgentMessage, AssistantMessage, RunChannel, RunResult,
    StopReason, ToolCall, ToolResult, ToolResultMessage, UserMessage,
    message_from_dict, message_to_dict,
)


__all__ = [
    'AgentEvent', 'AgentMessage', 'AgentRuntime', 'AfterToolCall', 'AssistantMessage',
    'BeforeToolCall', 'Checkpoint', 'CheckpointStore', 'Finish', 'ModelProvider',
    'ModelRequest', 'OpenAICompatProvider', 'ReasoningDelta', 'RunChannel', 'RunResult',
    'Skill', 'SkillRoot', 'SkillStore', 'StopReason', 'TextDelta', 'Tool', 'ToolCall',
    'ToolCallEvent', 'ToolOutput', 'ToolPolicy', 'ToolRegistry', 'ToolResult', 'ToolResultMessage',
    'ToolSpec', 'Usage', 'UserMessage', 'default_store', 'message_from_dict', 'message_to_dict',
    'tool',
]

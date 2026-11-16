"""Agent 基座公共出口；业务层只 from app.services.agent import ...

出口按「内核 / 能力」分区：内核 = types / tools / provider / memory / runtime，
外加技能装载入口（Skill/SkillStore/default_store，组合根必需）。
其余能力模块（ask_user / fetch_url / read_paper / netguard / chart_tools /
knowledge_tools / workspace / export / service）不经根出口再导出——使用方直接
import 对应模块，公共面不把中间件混进内核语义（docs/agent/README.md §3）。
"""
from app.services.agent.memory import Checkpoint, CheckpointStore
from app.services.agent.provider import (
    Finish, ModelProvider, ModelRequest, OpenAICompatProvider, ReasoningDelta, TextDelta, ToolCallEvent, Usage,
)
from app.services.agent.runtime import AgentRuntime
from app.services.agent.skills import Skill, SkillRoot, SkillStore, default_store
from app.services.agent.tools import (
    AfterToolCall, BeforeToolCall, Tool, ToolPolicy, ToolRegistry, ToolSpec, ToolOutput, tool,
)
from app.services.agent.types import (
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

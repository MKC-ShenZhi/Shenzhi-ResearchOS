"""Agent 基座公共出口；业务层只 from app.services.agent import ...

内核对中间件零依赖：这里再导出的 skills/workspace 属于"能力层"，由组合根按需装配。
"""
from app.services.agent.ask_user import AskUserArgs, QuestionOption, ask_user_tool
from app.services.agent.fetch_url import fetch_url_tool
from app.services.agent.netguard import BlockedUrlError, safe_get
from app.services.agent.provider import (
    Finish, ModelProvider, ModelRequest, OpenAICompatProvider, ReasoningDelta, TextDelta, ToolCallEvent, Usage,
)
from app.services.agent.read_paper import ReadPaperArgs, read_paper_tool
from app.services.agent.runtime import AgentRuntime
from app.services.agent.skills import (
    Skill, SkillRoot, SkillStore, default_store, read_skill_tool,
)
from app.services.agent.tools import (
    AfterToolCall, BeforeToolCall, FunctionTool, Tool, ToolOutput, ToolPolicy, ToolRegistry, ToolSpec, tool,
)
from app.services.agent.types import (
    AgentEvent, AgentMessage, AssistantMessage, FollowUpContext, NextTurn, RunChannel, RunResult,
    StopContext, StopReason, ToolCall, ToolResult, ToolResultMessage, UserMessage, message_from_dict,
    message_to_dict,
)

__all__ = [
    'AgentEvent', 'AgentMessage', 'AgentRuntime', 'AfterToolCall', 'AskUserArgs', 'AssistantMessage',
    'BeforeToolCall', 'BlockedUrlError', 'Finish', 'FollowUpContext', 'FunctionTool', 'ModelProvider',
    'ModelRequest', 'NextTurn', 'OpenAICompatProvider', 'QuestionOption', 'ReadPaperArgs',
    'ReasoningDelta', 'RunChannel', 'RunResult', 'Skill',
    'SkillRoot', 'SkillStore', 'StopContext', 'StopReason', 'TextDelta', 'Tool', 'ToolCall',
    'ToolCallEvent', 'ToolOutput', 'ToolPolicy', 'ToolRegistry', 'ToolResult', 'ToolResultMessage',
    'ToolSpec', 'Usage', 'UserMessage', 'ask_user_tool', 'default_store', 'fetch_url_tool',
    'message_from_dict', 'message_to_dict', 'read_paper_tool', 'read_skill_tool', 'safe_get', 'tool',
]

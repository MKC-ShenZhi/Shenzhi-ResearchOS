"""Tool 协议与注册表：一条错误规则 —— 任何失败都转 is_error 结果回喂模型自纠。

执行顺序（pi agent-loop.ts 源码核对）：参数校验 → before 钩子 → 执行 →
after 钩子；钩子自身异常同样转 is_error，绝不炸 run。
唯一例外：CancelledError 必须穿透（工具与钩子都不得吞取消）。
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.core.errors import BusinessError
from app.services.agent.types import ToolCall, ToolResult

TOOL_NAME = re.compile(r'^[a-z][a-z0-9_]{1,63}$')


@dataclass(frozen=True)
class ToolOutput:
    """工具返回值：content 进模型上下文；terminal 非 None 则直出为最终制品；
    added_tool_names 声明本次结果起可用的 latent 工具（pi addedToolNames）；
    unavailable 声明"本条能力当前不可用"（非查询错误，闸门据此让步）。"""

    content: str = ''
    terminal: Any = None
    added_tool_names: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema（OpenAI function 格式）
    timeout_s: float = 180.0
    params_model: type[BaseModel] | None = field(default=None, compare=False, repr=False)
    # 系统提示贡献（pi promptSnippet / promptGuidelines 机制）：snippet 是工具清单里的
    # 单行说明（缺省取 description 首句）；prompt_guidelines 是随工具挂载注入的专属准则。
    snippet: str = ''
    prompt_guidelines: tuple[str, ...] = ()
    # pi AgentTool.executionMode：'sequential'=该工具必须独占执行（批次中出现则整批顺序）。
    execution_mode: str | None = None


def _spec(name: str, description: str, params: type[BaseModel] | None, timeout_s: float,
          snippet: str = '', prompt_guidelines: tuple[str, ...] = (),
          execution_mode: str | None = None) -> ToolSpec:
    schema = params.model_json_schema() if params is not None else {'type': 'object', 'properties': {}}
    return ToolSpec(name, description, schema, timeout_s, params, snippet, prompt_guidelines,
                    execution_mode)


class Tool(Protocol):
    spec: ToolSpec

    async def execute(self, call: ToolCall, args: Any) -> str | ToolOutput: ...
    # 实现约定：失败一律 raise（含 BusinessError），禁止返回错误文本冒充结果


class FunctionTool:
    """把函数包装成 Tool；params 非 None 时函数接收校验后的模型实例，否则无参。"""

    def __init__(self, name: str, description: str, func: Callable,
                 params: type[BaseModel] | None = None, *, timeout_s: float = 180.0,
                 snippet: str = '', prompt_guidelines: tuple[str, ...] = (),
                 execution_mode: str | None = None):
        self.spec = _spec(name, description, params, timeout_s, snippet, prompt_guidelines,
                          execution_mode)
        self._func = func

    async def execute(self, call: ToolCall, args: Any) -> str | ToolOutput:
        result = self._func(args) if self.spec.params_model is not None else self._func()
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, (str, ToolOutput)):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)


def tool(*, name: str, description: str, params: type[BaseModel] | None = None,
         timeout_s: float = 180.0, snippet: str = '', prompt_guidelines: tuple[str, ...] = (),
         execution_mode: str | None = None) -> Callable[[Callable], FunctionTool]:
    """装饰器：把 async 函数定义为基座 Tool；snippet/prompt_guidelines 进系统提示。"""

    def register(func: Callable) -> FunctionTool:
        return FunctionTool(name, description, func, params, timeout_s=timeout_s,
                            snippet=snippet, prompt_guidelines=prompt_guidelines,
                            execution_mode=execution_mode)

    return register


# 钩子拿到的是校验后的 args；before 返回 ToolResult 表示阻断（is_error 带原因），None 放行；
# after 返回 None 保留原结果（与 pi AfterToolCallResult|undefined 语义一致）
BeforeToolCall = Callable[[ToolCall, Any], Awaitable[ToolResult | None]]
AfterToolCall = Callable[[ToolCall, Any, ToolResult], Awaitable[ToolResult | None]]


class ToolPolicy(Protocol):
    """工具执行的策略扩展点（内核对具体策略零依赖的边界）。

    设计依据 pi：循环对技能一无所知，一切工具行为差异走钩子（`agent-loop.ts` 的
    prepareToolCall before 分支）。本协议就是那对钩子的最小形状，由能力层实现
    （如 skills.SkillPolicy 提供 read_skill 的重复装载拦截与 pinned 预算），
    由组合根装配进 runtime——因此 `runtime.py` 不需要 import 任何能力模块。

    - intercept：执行前判定；返回结果则短路（通常是 is_error 回喂），None 放行；
    - settle：执行后结算（可替换结果，如给结果打 pinned 标记、计入预算）。
    """

    def intercept(self, call: ToolCall, state: Any) -> ToolResult | None: ...

    def settle(self, call: ToolCall, result: ToolResult, state: Any) -> ToolResult: ...


@dataclass(frozen=True)
class PreparedCall:
    """校验与 before 钩子已通过、待执行的工具调用（pi PreparedToolCall）。"""
    call: ToolCall
    tool: Tool
    args: Any


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool], *, latent: Iterable[str] = ()):
        """latent：注册但未启用的工具名（不出现在 wire 与系统提示），由工具结果的
        added_tool_names 按需启用（pi addedToolNames 语义）。"""
        self.tools: dict[str, Tool] = {}
        for item in tools:
            if not TOOL_NAME.match(item.spec.name) or item.spec.name in self.tools:
                raise ValueError(f'非法或重复的工具名: {item.spec.name}')
            self.tools[item.spec.name] = item
        unknown = set(latent) - set(self.tools)
        if unknown:
            raise ValueError(f'latent 工具未注册: {", ".join(sorted(unknown))}')
        self.latent: set[str] = set(latent)

    @property
    def enabled(self) -> list[str]:
        return [name for name in self.tools if name not in self.latent]

    def enable(self, names: Iterable[str]) -> list[str]:
        """启用 latent 工具，返回本次实际启用的名字（未知/已启用忽略）。"""
        activated = []
        for name in names:
            if name in self.latent:
                self.latent.discard(name)
                activated.append(name)
        return activated

    def wire(self, names: Sequence[str] | None = None) -> list[dict]:
        """OpenAI tools 参数；names 指定启用集（run 级动态启用的快照），空列表表示不带工具。"""
        chosen = self.enabled if names is None else list(names)
        return [{'type': 'function', 'function': {
            'name': self.tools[name].spec.name, 'description': self.tools[name].spec.description,
            'parameters': self.tools[name].spec.parameters,
        }} for name in chosen]

    async def prepare(self, call: ToolCall, *,
                      before: BeforeToolCall | None = None) -> PreparedCall | ToolResult:
        """校验 + before 钩子（pi prepareToolCall：validate → before）。
        返回 ToolResult 表示立即结果（未知工具/校验失败/钩子阻断），PreparedCall 待执行。"""
        target = self.tools.get(call.name)
        if target is None:
            # pi agent-loop.ts:618 原句
            return ToolResult(call.call_id, call.name, f'Tool {call.name} not found', is_error=True)
        # 参数已是对象（provider 在 AI 层解析）；这里做的是"执行前校验"，
        # 模型给的对象仍然不被信任——过不了 pydantic 就 is_error 回喂。
        try:
            args: Any = (target.spec.params_model.model_validate(call.arguments)
                         if target.spec.params_model is not None else {})
        except ValidationError as exc:
            return ToolResult(call.call_id, call.name, f'工具参数校验失败: {str(exc)[:500]}', is_error=True)
        if before is not None:
            try:
                blocked = await before(call, args)
            except Exception as exc:  # 钩子异常 → is_error，不炸 run
                return ToolResult(call.call_id, call.name, f'before_tool_call 失败: {exc}', is_error=True)
            if blocked is not None:
                return blocked
        return PreparedCall(call, target, args)

    async def execute_prepared(self, prepared: PreparedCall, *,
                               after: AfterToolCall | None = None) -> ToolResult:
        """执行已准备好的调用（每工具超时 → is_error）+ after 钩子（可改写结果）。"""
        call, target = prepared.call, prepared.tool
        try:
            async with asyncio.timeout(target.spec.timeout_s):
                output = await target.execute(call, prepared.args)
        except TimeoutError:
            return ToolResult(call.call_id, call.name,
                              f'工具执行超时（{target.spec.timeout_s:.0f}s），请调整参数或放弃该步骤',
                              is_error=True)
        except asyncio.CancelledError:
            raise
        except BusinessError as exc:
            return ToolResult(call.call_id, call.name, exc.message, is_error=True)
        except Exception as exc:
            return ToolResult(call.call_id, call.name, f'工具执行失败: {exc}', is_error=True)
        if isinstance(output, ToolOutput):
            result = ToolResult(call.call_id, call.name, output.content,
                                terminal=output.terminal, added_tool_names=output.added_tool_names,
                                unavailable=output.unavailable)
        else:
            result = ToolResult(call.call_id, call.name, str(output))
        if after is not None:
            try:
                replaced = await after(call, prepared.args, result)
            except Exception as exc:
                return ToolResult(call.call_id, call.name, f'after_tool_call 失败: {exc}', is_error=True)
            if replaced is not None:
                return replaced
        return result

    async def dispatch(self, call: ToolCall, *,
                       before: BeforeToolCall | None = None,
                       after: AfterToolCall | None = None) -> ToolResult:
        """顺序便捷路径：prepare + execute_prepared（语义与拆分版完全一致）。"""
        prepared = await self.prepare(call, before=before)
        if isinstance(prepared, ToolResult):
            return prepared
        return await self.execute_prepared(prepared, after=after)

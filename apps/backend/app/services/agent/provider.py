"""OpenAI 兼容流式 Provider：SSE 解析、tool_calls 归并、零增量单次重试。

对应 pi-ai 的 AssistantMessageEventStream 层，按服务端需要裁剪：不做
contentIndex 级的 start/end 事件，tool_calls 归并完在流尾一次性产出。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from app.core.config import ModelConfig, model_config
from app.core.errors import BusinessError
from app.services.agent.json_repair import parse_streaming_json
from app.services.agent.types import StopReason, ToolCall

REASONING_MODEL = re.compile(r'reasoner|r1|qwen3', re.I)
# 可重试状态码（pi provider-retry.ts:23-35）：408/409/429/≥500。
# 400 不在其中——它是参数/内容错误，重试必然复现；此前把 400 加进来是为了兜住一次
# 未确诊的线上失败，根因（截断的 function.arguments 原样回传）已在 json_repair 层修掉，
# 因此回到 pi 的口径。`x-should-retry` 响应头有一票裁决权（pi 同机制）。
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
RETRY_MIN_REMAINING_S = 2.0  # 剩余 deadline 不足时重试只会白耗预算，直接失败
RETRY_JITTER = 0.25          # pi：退避加 25% 抖动，避免同批客户端同时重连
# 明确的额度/账单类错误不重试（pi utils/retry.ts:7-90 的错误文本分类）
_NON_RETRYABLE_MARKERS = ('insufficient_quota', 'insufficient quota', 'billing', 'arrears',
                          'quota exceeded', 'balance')

_STATUS_MESSAGES = {
    401: '模型服务凭据无效，请联系管理员',
    403: '模型服务无访问权限',
    429: '模型服务限流或额度不足，请稍后重试',
    400: '模型不支持当前请求参数',
}

# finish_reason → 停止原因（pi openai-completions.ts:1550-1574）：
# 未知取值与 content_filter 一律判 error 并保留原文，不静默降级成 stop——
# 静默降级会让"被内容审核截断"看起来像"模型正常说完了"。
_FINISH_REASONS = {
    'stop': StopReason.STOP,
    'length': StopReason.LENGTH,
    'tool_calls': StopReason.TOOL_CALLS,
    'function_call': StopReason.TOOL_CALLS,
}


# 单次输出上限：DashScope 对 qwen-plus 的硬顶（实测 max_tokens>32768 直接 400：
# "Range of max_tokens should be [1, 32768]"）。此前用 8192 只发挥了 1/4，
# 而思考与正文共享这个额度——报告写不长的机械原因就在这。拉满到平台顶。
MAX_OUTPUT_TOKENS = 32768


@dataclass(frozen=True)
class ModelRequest:
    model: str
    messages: list[dict]
    tools: list[dict] = field(default_factory=list)
    temperature: float | None = None
    max_tokens: int = MAX_OUTPUT_TOKENS
    deadline_at: float | None = None  # time.monotonic() 截止点；剩余不足时不再重试


@dataclass(frozen=True)
class Usage:
    """一次请求的用量（pi ai/types.ts Usage 的字段子集）。

    cache_read/reasoning 来自 OpenAI 兼容响应的 *_tokens_details；
    total_tokens 缺省时按 input+output 兜底。pi 还算 cost（依赖内置模型价目表），
    我们没有价目表就不编造数字——需要成本时由业务层按自己的价目折算。
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True)
class ToolCallEvent:
    call: ToolCall


@dataclass(frozen=True)
class Finish:
    stop_reason: StopReason
    usage: Usage | None = None
    # pi：未知/被审核的 finish_reason 映射为 error，并保留上游说明
    # （openai-completions.ts:1550-1574 的 errorMessage），
    # 否则"被内容审核截断"会伪装成"模型正常说完"。原始取值只进日志，不进契约。
    error_message: str = ''


ProviderEvent = TextDelta | ReasoningDelta | ToolCallEvent | Finish


class ModelProvider(Protocol):
    """stream 必须是 async 生成器（runtime 用 aclosing 确定性关闭连接）。"""

    def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]: ...


def _parse_usage(raw: dict) -> Usage:
    """pi openai-completions.ts:1507-1548 parseChunkUsage 的字段口径。

    cache_read 依次取 prompt_tokens_details.cached_tokens / prompt_cache_hit_tokens /
    顶层 cached_tokens（各家兼容层字段名不统一）；reasoning 取
    completion_tokens_details.reasoning_tokens；total 缺省时按 input+output 兜底。
    """
    prompt = _as_int(raw.get('prompt_tokens'))
    completion = _as_int(raw.get('completion_tokens'))
    prompt_details = raw.get('prompt_tokens_details')
    completion_details = raw.get('completion_tokens_details')
    prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
    completion_details = completion_details if isinstance(completion_details, dict) else {}
    cache_read = _as_int(prompt_details.get('cached_tokens')
                         or raw.get('prompt_cache_hit_tokens') or raw.get('cached_tokens'))
    reasoning = _as_int(completion_details.get('reasoning_tokens'))
    total = _as_int(raw.get('total_tokens')) or (prompt + completion)
    return Usage(prompt_tokens=prompt, completion_tokens=completion,
                 cache_read_tokens=cache_read,
                 reasoning_tokens=reasoning, total_tokens=total)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class _UpstreamStatus(Exception):
    def __init__(self, status: int, detail: str = '', headers: Mapping[str, str] | None = None):
        super().__init__(str(status))
        self.status = status
        self.detail = detail
        self.headers = dict(headers or {})


def _retryable_status(status: int, headers: Mapping[str, str], detail: str) -> bool:
    """该不该重试（pi provider-retry.ts + utils/retry.ts 的判定合并）。

    优先级：`x-should-retry` 头一票裁决 → 额度/账单类文本明确不重试 → 状态码集合。
    """
    header = str(headers.get('x-should-retry', '')).lower()
    if header in ('true', 'false'):
        return header == 'true'
    lowered = detail.lower()
    if any(marker in lowered for marker in _NON_RETRYABLE_MARKERS):
        return False
    return status in RETRYABLE_STATUS or status >= 500


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """服务端要求的等待时长：`retry-after-ms` 优先，其次 `Retry-After`（秒或 HTTP-date）。"""
    millis = headers.get('retry-after-ms')
    if millis:
        try:
            return max(0.0, float(millis) / 1000.0)
        except ValueError:
            pass
    raw = headers.get('retry-after')
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def _status_error(status: int, detail: str = '') -> BusinessError:
    """上游状态 → 业务错误。detail（上游响应体摘要）随消息带出：
    400 的原因（参数不支持 / 输入超限 / 消息序列非法）只有上游说得清，丢掉它就只能猜。"""
    message = _STATUS_MESSAGES.get(status, f'模型服务暂不可用（HTTP {status}）')
    if detail:
        message = f'{message}（上游：{detail[:200]}）'
    return BusinessError(20004, message, 502)


class OpenAICompatProvider:
    """唯一内置实现：任意 OpenAI 兼容 /chat/completions 端点（DashScope/DeepSeek/代理）。

    max_retries 为零增量重试上限（默认 1，pi 重试策略的裁剪版）；退避 retry_delay×2^n
    封顶 max_retry_delay。on_payload/on_response 是 wire 层观测钩子（pi onPayload/onResponse），
    默认关闭，异常不影响请求。
    """

    def __init__(self, config: ModelConfig | None = None, *,
                 transport: httpx.AsyncBaseTransport | None = None, retry_delay: float = 1.5,
                 max_retries: int = 2, max_retry_delay: float = 24.0,
                 on_payload: Callable[[dict], None] | None = None,
                 on_response: Callable[[dict | None], None] | None = None):
        self.config = config or model_config()
        self.transport = transport
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.max_retry_delay = max_retry_delay
        self.on_payload = on_payload
        self.on_response = on_response

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        if not self.config.key:
            raise BusinessError(20004, '后端未配置 DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY', 503)
        attempt = 0
        while True:
            attempt += 1
            emitted = False
            retry_after: float | None = None
            try:
                async for event in self._stream_once(request):
                    emitted = True
                    yield event
                return
            except _UpstreamStatus as exc:
                retryable = _retryable_status(exc.status, exc.headers, exc.detail)
                if not retryable or attempt > self.max_retries or not self._time_for_retry(request):
                    raise _status_error(exc.status, exc.detail) from exc
                retry_after = _retry_after_seconds(exc.headers)
            except httpx.TimeoutException:
                if emitted or attempt > self.max_retries or not self._time_for_retry(request):
                    raise BusinessError(20004, '模型响应超时，可以继续生成', 504) from None
            except httpx.HTTPError:
                if emitted or attempt > self.max_retries or not self._time_for_retry(request):
                    raise BusinessError(20004, '模型连接中断，可以继续生成', 502) from None
            await asyncio.sleep(self._retry_delay_seconds(attempt, retry_after))

    def _retry_delay_seconds(self, attempt: int, retry_after: float | None) -> float:
        """退避：服务端给的延迟优先（pi retry-after-ms / Retry-After），
        否则 1.5·2^n 封顶 max_retry_delay，并加 25% 抖动避免同批客户端同时重连。"""
        base = (retry_after if retry_after is not None
                else min(self.retry_delay * 2 ** (attempt - 1), self.max_retry_delay))
        return base * (1 + random.random() * RETRY_JITTER)

    @staticmethod
    def _time_for_retry(request: ModelRequest) -> bool:
        """零增量重试条件之一：剩余 deadline > 2s（无 deadline 视为充裕）。"""
        if request.deadline_at is None:
            return True
        return request.deadline_at - time.monotonic() > RETRY_MIN_REMAINING_S

    @staticmethod
    def _observe(hook: Callable[[Any], None] | None, data: Any) -> None:
        """观测钩子（pi onPayload/onResponse）：纯观察，异常绝不影响请求。"""
        if hook is None:
            return
        try:
            hook(data)
        except Exception:
            logging.getLogger('app.agent').exception('provider 观测钩子失败（已忽略）')

    def _build_payload(self, request: ModelRequest, *, thinking: bool = True,
                       include_usage: bool = True) -> dict:
        reasoning = bool(REASONING_MODEL.search(request.model))
        payload: dict = {
            'model': request.model,
            'messages': request.messages,
            'stream': True,
            'max_tokens': MAX_OUTPUT_TOKENS if reasoning else request.max_tokens,
        }
        if request.tools:
            payload['tools'] = request.tools
            payload['tool_choice'] = 'auto'
        if request.temperature is not None and not reasoning:
            payload['temperature'] = request.temperature
        # 流式响应默认不带 usage 尾帧，必须显式索要（pi openai-completions.ts:818-820）；
        # 拿不到真实用量，compaction 的触发估算就只能退回纯字符启发式。
        if include_usage:
            payload['stream_options'] = {'include_usage': True}
        # 思维链开关（pi thinkingLevel 的裁剪版）：DashScope 平台传 enable_thinking
        # 让 qwen-plus 等输出 reasoning_content（deepseek-reasoner 等原生思维链模型不需要）。
        # 默认开（产品要求思考过程可见）；AGENT_DISABLE_THINKING=true 可关。
        if (thinking and self.config.provider == 'platform' and not reasoning
                and os.getenv('AGENT_DISABLE_THINKING', '').strip().lower() != 'true'):
            payload['enable_thinking'] = True
            payload['max_tokens'] = MAX_OUTPUT_TOKENS  # 平台顶；思考与正文共享这个额度
        return payload

    async def _stream_once(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        # 400 降级阶梯（pi 无此需求，因为我们只对接单一平台）：可选增强项逐个摘掉重试，
        # 增强不得绑架主流程。顺序 = **先摘思维链，再摘 usage 尾帧**：实测上游 400 的原文
        # 是 "enable_thinking not supported"（平台差异基本都出在思维链开关上），
        # 先摘 stream_options 会白耗一次尝试。
        # 回归：test_thinking_dropped_on_400_before_outer_retry。
        degradations = ('enable_thinking', 'stream_options')
        dropped: set[str] = set()
        timeout = httpx.Timeout(float(os.getenv('AI_TIMEOUT_SEC', '90')), connect=10)
        while True:
            payload = self._build_payload(request, thinking='enable_thinking' not in dropped,
                                          include_usage='stream_options' not in dropped)
            usage: Usage | None = None
            tool_calls: dict[int, dict[str, str]] = {}
            finish_text: str | None = None
            finished = False
            self._observe(self.on_payload, payload)
            try:
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                    async with client.stream(
                        'POST', f'{self.config.base_url}/chat/completions',
                        headers={'Authorization': f'Bearer {self.config.key}', 'Accept': 'text/event-stream'},
                        json=payload,
                    ) as response:
                        if response.status_code >= 400:
                            # 上游响应体是唯一的权威解释（参数不支持/输入超限/消息序列非法），
                            # 必须在抛错前读出来——否则只剩一句无从下手的通用文案。
                            detail = (await response.aread()).decode('utf-8', 'replace')
                            next_drop = next((name for name in degradations
                                              if name not in dropped and name in payload), None)
                            if response.status_code == 400 and next_drop is not None:
                                dropped.add(next_drop)
                                logging.getLogger('app.agent').warning(
                                    '%s 被上游拒绝(400)，摘掉后重试：%s', next_drop, detail[:300])
                                continue
                            logging.getLogger('app.agent').warning(
                                '模型上游返回 %s：%s', response.status_code, detail[:500])
                            raise _UpstreamStatus(response.status_code, detail, response.headers)
                        async for line in response.aiter_lines():
                            if not line.startswith('data:'):
                                continue
                            raw = line[5:].strip()
                            if not raw:
                                continue
                            if raw == '[DONE]':
                                finished = True
                                break
                            try:
                                data = json.loads(raw)
                            except ValueError:
                                raise BusinessError(20004, '模型流数据格式错误', 502) from None
                            self._observe(self.on_response, data)
                            if data.get('error'):
                                raise BusinessError(20004, '模型流返回错误，请稍后重试', 502)
                            if isinstance(data.get('usage'), dict):
                                usage = _parse_usage(data['usage'])
                            choices = data.get('choices') or []
                            if not choices:
                                continue
                            choice = choices[0]
                            delta = choice.get('delta') or {}
                            if isinstance(delta.get('content'), str) and delta['content']:
                                yield TextDelta(delta['content'])
                            if isinstance(delta.get('reasoning_content'), str) and delta['reasoning_content']:
                                yield ReasoningDelta(delta['reasoning_content'])
                            for fragment in delta.get('tool_calls') or []:
                                if not isinstance(fragment, dict):
                                    continue
                                index = fragment.get('index') or 0
                                entry = tool_calls.setdefault(index, {'id': '', 'name': '', 'arguments': ''})
                                # 首帧带 id/name，后续帧通常只有 arguments 片段；
                                # 供应商重复发送 id/name 时赋值覆盖天然容错。
                                if isinstance(fragment.get('id'), str) and fragment['id']:
                                    entry['id'] = fragment['id']
                                function = fragment.get('function') or {}
                                if isinstance(function.get('name'), str) and function['name']:
                                    entry['name'] = function['name']
                                if isinstance(function.get('arguments'), str):
                                    entry['arguments'] += function['arguments']
                            if choice.get('finish_reason'):
                                finish_text = str(choice['finish_reason'])
                                finished = True
                        if not finished:
                            raise BusinessError(20004, '模型流提前结束，可以继续生成', 502)
                        for index in sorted(tool_calls):
                            entry = tool_calls[index]
                            if entry['name']:
                                # 参数在 AI 层解析成对象（pi toolcall_end 定稿同位置）：
                                # 残缺 JSON 走修复阶梯、保留已写完的字段，绝不抛错——
                                # 因此下游拿到的参数恒为对象，回传上游时恒为合法 JSON。
                                yield ToolCallEvent(ToolCall(entry['id'] or f'call_{index}',
                                                             entry['name'],
                                                             parse_streaming_json(entry['arguments'])))
                        raw_reason = finish_text or ''
                        stop = _FINISH_REASONS.get(raw_reason)
                        error_message = ''
                        if stop is None:
                            if not raw_reason:
                                # 流正常收尾但上游没给 finish_reason：按内容推断（pi compat 分支）
                                stop = StopReason.TOOL_CALLS if tool_calls else StopReason.STOP
                            else:
                                # content_filter / 未知取值 → error 并保留原文（pi:1550-1574）；
                                # 静默降级成 stop 会让"被审核截断"伪装成"正常说完"
                                stop = StopReason.ERROR
                                error_message = f'模型返回未知停止原因: {raw_reason}'
                        yield Finish(stop, usage, error_message=error_message)
            except BusinessError:
                raise
            except (ValueError, TypeError, AttributeError, IndexError, KeyError) as exc:
                raise BusinessError(20004, '模型流数据格式错误', 502) from exc
            return  # 本轮流式完成，退出重试循环（否则 while True 会再发一次请求）

"""B's OpenAI-compatible streaming adapter, now entirely in FastAPI.

Only standard chat/completions fields are sent. Upstream token/thinking
payloads are translated here into the single product delta schema.
"""
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from time import perf_counter
import httpx
from app.core.config import ModelConfig
from app.integrations.llm.registry import ModelRegistry, ModelSpec
from app.integrations.llm.resolver import load_registry, model_definition, registry_from_legacy
from app.core.errors import BusinessError
from app.core.logging import log_event

TEMPERATURE = {'fast': 0.3, 'deep': 0.6, 'idea': 1.0, 'doubt': 0.85}
logger = logging.getLogger(__name__)


def resolve_model(raw: str | None, config: ModelConfig | None = None) -> str:
    registry = registry_from_legacy(config) if config is not None else load_registry()
    return registry.resolve_model(raw, require_configured=False).spec.id


def completion_payload(model: ModelSpec | str, messages: list[dict], mode: str) -> dict:
    # String input is retained for existing server-side adapter tests.
    spec = model if isinstance(model, ModelSpec) else model_definition(model, 'deepseek', model)
    caps = spec.capabilities
    payload = {'model': spec.upstream_model, 'messages': messages, 'stream': True,
               'max_tokens': min(caps.chat_max_tokens, caps.max_output_tokens)}
    if caps.temperature:
        payload['temperature'] = TEMPERATURE.get(mode, 0.3)
    payload.update(spec.request_params)
    return payload


def provider_error(status: int) -> BusinessError:
    messages = {401: '模型服务凭据无效，请联系管理员', 403: '模型服务无访问权限',
                429: '模型服务限流或额度不足，请稍后重试', 400: '模型不支持当前请求参数'}
    return BusinessError(20004, messages.get(status, f'模型服务暂不可用（HTTP {status}）'), 502)


class ModelProvider:
    def __init__(self, config: ModelConfig | None = None, transport=None, *,
                 registry: ModelRegistry | None = None):
        self.registry = registry or (registry_from_legacy(config) if config is not None else load_registry())
        self.transport = transport

    async def stream(self, messages: list[dict], model: str, mode: str) -> AsyncIterator[dict]:
        started_at = perf_counter()
        status_code: int | None = None
        resolved = None
        try:
            resolved = self.registry.resolve_model(model)
            payload = completion_payload(resolved.spec, messages, mode)
            timeout = httpx.Timeout(float(os.getenv('AI_TIMEOUT_SEC', '90')), connect=10)
            finished = False
            try:
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                    async with client.stream('POST', f'{resolved.base_url}/chat/completions',
                            headers={'Authorization': f'Bearer {resolved.key}', 'Accept': 'text/event-stream'},
                            json=payload) as response:
                        status_code = response.status_code
                        if response.status_code >= 400:
                            raise provider_error(response.status_code)
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
                                if data.get('error'):
                                    raise BusinessError(20004, '模型流返回错误，请稍后重试', 502)
                                choices = data.get('choices') or []
                                if not choices:
                                    continue
                                choice = choices[0]
                                delta = choice.get('delta') or {}
                                event = {}
                                if isinstance(delta.get('content'), str):
                                    event['text'] = delta['content']
                                if isinstance(delta.get('reasoning_content'), str):
                                    event['reasoning'] = delta['reasoning_content']
                                if event:
                                    yield event
                                if choice.get('finish_reason'):
                                    finished = True
                            except (ValueError, TypeError, AttributeError, IndexError) as exc:
                                raise BusinessError(20004, '模型流数据格式错误', 502) from exc
            except httpx.TimeoutException as exc:
                raise BusinessError(20004, '模型响应超时，可以继续生成', 504) from exc
            except httpx.HTTPError as exc:
                raise BusinessError(20004, '模型连接中断，可以继续生成', 502) from exc
            if not finished:
                raise BusinessError(20004, '模型流提前结束，可以继续生成', 502)
        except Exception as error:
            log_event(logger, logging.ERROR, 'llm.request.failed', {
                'provider': resolved.provider.spec.id if resolved else 'unresolved',
                'operation': 'chat.completions.stream',
                'status_code': status_code,
                'duration_ms': round((perf_counter() - started_at) * 1000),
                'error_type': type(error).__name__,
                'error_code': getattr(error, 'code', None),
            })
            raise
        else:
            log_event(logger, logging.INFO, 'llm.request.completed', {
                'provider': resolved.provider.spec.id if resolved else 'unresolved',
                'operation': 'chat.completions.stream',
                'status_code': status_code,
                'duration_ms': round((perf_counter() - started_at) * 1000),
            })

    async def followups(self, question: str, answer: str) -> list[str]:
        if len(answer) < 20:
            return []
        started_at = perf_counter()
        messages = [
            {'role': 'system', 'content': '根据用户问题和回答生成三个紧扣话题、由浅入深的追问。只返回 JSON 字符串数组。'},
            {'role': 'user', 'content': question},
            {'role': 'assistant', 'content': answer[:1500]},
            {'role': 'user', 'content': '请生成 3 个追问，只返回 JSON 数组。'},
        ]
        resolved = None
        try:
            resolved = self.registry.resolve_model(None)
            payload = completion_payload(resolved.spec, messages, 'fast')
            payload.update(stream=False, max_tokens=min(300, resolved.spec.capabilities.max_output_tokens))
            async with httpx.AsyncClient(timeout=10, transport=self.transport) as client:
                response = await client.post(f'{resolved.base_url}/chat/completions',
                    headers={'Authorization': f'Bearer {resolved.key}'}, json=payload)
                response.raise_for_status()
                raw = response.json()['choices'][0]['message']['content']
                match = re.search(r'\[[\s\S]*?\]', raw)
                parsed = json.loads(match.group()) if match else []
            result = (
                [s.strip()[:200] for s in parsed if isinstance(s, str) and s.strip()][:3]
                if isinstance(parsed, list) else []
            )
            log_event(logger, logging.INFO, 'llm.request.completed', {
                'provider': resolved.provider.spec.id if resolved else 'unresolved',
                'operation': 'chat.completions.followups',
                'status_code': response.status_code,
                'duration_ms': round((perf_counter() - started_at) * 1000),
            })
            return result
        except (BusinessError, httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            log_event(logger, logging.ERROR, 'llm.request.failed', {
                'provider': resolved.provider.spec.id if resolved else 'unresolved',
                'operation': 'chat.completions.followups',
                'duration_ms': round((perf_counter() - started_at) * 1000),
                'error_type': type(error).__name__,
            })
            return []  # Optional followups must not fail a completed answer.

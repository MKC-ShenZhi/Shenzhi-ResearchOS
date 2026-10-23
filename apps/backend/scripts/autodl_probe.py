"""Small, credential-safe AutoDL compatibility probe (stdout is one JSON report).

Run with uv run --env-file .env python scripts/autodl_probe.py --list-only
first, then pass exact IDs as positional arguments. Only httpx is required.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import sys
from urllib.parse import urlsplit

import httpx

DEFAULT_BASE_URL = 'https://www.autodl.art/api/v1'
WRONG_KEY = 'invalid-autodl-probe-key'
ECHO = {'type': 'function', 'function': {
    'name': 'echo', 'description': 'Echo text.',
    'parameters': {'type': 'object', 'properties': {'text': {'type': 'string'}},
                   'required': ['text'], 'additionalProperties': False},
}}


def redact(text: str, key: str) -> str:
    # Also remove partially echoed credentials before truncating the error body.
    for secret in (key, key[:8], WRONG_KEY):
        if secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)bearer\s+[^\s"<>]+', 'Bearer [REDACTED]', text)
    return re.sub(r'(?i)(api[_-]?key|token|authorization)(["\s:=]+)[^\s",}<>]+',
                  r'\1\2[REDACTED]', text)


class Probe:
    def __init__(self, client: httpx.Client, base_url: str, key: str):
        self.client, self.base_url, self.key = client, base_url, key

    def models(self) -> dict:
        try:
            response = self.client.get(f'{self.base_url}/models',
                                       headers={'Authorization': f'Bearer {self.key}'})
            result = {'status': response.status_code, 'ids': []}
            if response.status_code == 200:
                result['ids'] = [item['id'] for item in response.json().get('data', [])
                                 if isinstance(item, dict) and isinstance(item.get('id'), str)]
            else:
                result['error_body'] = redact(response.text, self.key)[:200]
            return result
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            return {'status': None, 'ids': [], 'error_type': type(exc).__name__}

    def stream(self, model: str, *, messages: list[dict] | None = None,
               first_chunk: bool = False, **params) -> dict:
        payload = {'model': model, 'stream': True, 'max_tokens': 4096,
                   'messages': messages or [{'role': 'user', 'content': 'Reply OK.'}], **params}
        result = {'status': None, 'content_nonempty': False, 'finish_reasons': [],
                  'reasoning_content': False, 'reasoning': False, 'think_tag': False,
                  'usage': False, 'tool_call_fragments': 0, 'completed': False}
        content: list[str] = []
        calls: dict[int, dict] = {}
        try:
            with self.client.stream('POST', f'{self.base_url}/chat/completions',
                    headers={'Authorization': f'Bearer {self.key}', 'Accept': 'text/event-stream'},
                    json=payload) as response:
                result['status'] = response.status_code
                if response.status_code != 200:
                    response.read()
                    result['error_body'] = redact(response.text, self.key)[:200]
                    return result
                for line in response.iter_lines():
                    if not line.startswith('data:') or not line[5:].strip():
                        continue
                    if first_chunk:
                        result['first_chunk_received'] = True
                        break  # Close the response immediately, including token-limit probes.
                    raw = line[5:].strip()
                    if raw == '[DONE]':
                        result['completed'] = True
                        break
                    data = json.loads(raw)
                    if data.get('error'):
                        result['stream_error'] = True
                        break
                    result['usage'] |= isinstance(data.get('usage'), dict) and bool(data['usage'])
                    choices = data.get('choices') or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get('delta') or {}
                    for field in ('reasoning_content', 'reasoning'):
                        result[field] |= field in delta
                    if isinstance(delta.get('content'), str):
                        content.append(delta['content'])
                    reason = choice.get('finish_reason')
                    if reason is not None:
                        result['finish_reasons'].append(reason)
                        result['completed'] = True
                    for fragment in delta.get('tool_calls') or []:
                        result['tool_call_fragments'] += 1
                        call = calls.setdefault(fragment.get('index', 0), {
                            'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                        if fragment.get('id'):
                            call['id'] = fragment['id']
                        function = fragment.get('function') or {}
                        if function.get('name'):
                            call['function']['name'] = function['name']
                        if isinstance(function.get('arguments'), str):
                            call['function']['arguments'] += function['arguments']
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError) as exc:
            result['error_type'] = type(exc).__name__
        text = ''.join(content)
        result.update(content_nonempty=bool(text.strip()), think_tag='<think>' in text.lower())
        # Private values are needed for the second tool turn; never print raw generated text.
        result['_content'] = text
        result['_calls'] = [calls[index] for index in sorted(calls)]
        return result

    def tool_run(self, model: str, params: dict) -> dict:
        messages = [{'role': 'user', 'content': 'Must call echo(text="ok") once. Then reply OK.'}]
        first = self.stream(model, messages=messages, tools=[ECHO], tool_choice='auto', **params)
        calls = first.get('_calls', [])
        valid = bool(calls)
        results = []
        for call in calls:
            try:
                args = json.loads(call['function']['arguments'])
                valid &= (bool(call['id']) and call['function']['name'] == 'echo'
                          and isinstance(args, dict) and isinstance(args.get('text'), str))
                results.append({'role': 'tool', 'tool_call_id': call['id'],
                                'content': json.dumps(args.get('text'), ensure_ascii=False)})
            except (ValueError, TypeError, AttributeError):
                valid = False
        result = {'round1': public(first), 'arguments_valid_json': bool(valid), 'pass': False}
        if not (stream_ok(first) and valid and first['tool_call_fragments']):
            return result
        # Intentionally omit reasoning_content/reasoning, matching Agent's saved history.
        messages += [{'role': 'assistant', 'content': first.get('_content') or None,
                      'tool_calls': calls}, *results]
        second = self.stream(model, messages=messages, tools=[ECHO], tool_choice='auto', **params)
        result['round2'] = public(second)
        result['pass'] = stream_ok(second) and second['content_nonempty']
        return result

    def tools(self, model: str, params: dict) -> dict:
        runs = [self.tool_run(model, params) for _ in range(2)]
        return {'request_params': params, 'runs': runs, 'pass': all(run['pass'] for run in runs)}

    def error(self, model: str) -> dict:
        try:
            response = self.client.post(f'{self.base_url}/chat/completions',
                headers={'Authorization': f'Bearer {WRONG_KEY}'}, json={
                    'model': model, 'messages': [{'role': 'user', 'content': 'OK'}], 'max_tokens': 1})
            return {'status': response.status_code, 'body_prefix': redact(response.text, self.key)[:200]}
        except httpx.HTTPError as exc:
            return {'status': None, 'error_type': type(exc).__name__}


def stream_ok(result: dict) -> bool:
    return (result['status'] == 200 and result['completed']
            and not result.get('error_type') and not result.get('stream_error')
            and not result['think_tag'])


def public(result: dict) -> dict:
    return {name: value for name, value in result.items() if not name.startswith('_')}


def run(probe: Probe, models: list[str], *, list_only: bool = False) -> dict:
    report = {'probed_at': datetime.now(timezone.utc).isoformat(), 'T0': probe.models(), 'models': {}}
    ids = report['T0']['ids']
    if report['T0']['status'] != 200:
        report['stop_reason'] = 'T0 请求失败，无法确认模型列表'
        return report
    if not any('deepseek' in name.lower() and re.search(r'v4[.\-]?1', name.lower()) for name in ids):
        report['stop_reason'] = 'T0 中找不到 DeepSeek V4.1，停止探测'
        return report
    if list_only:
        return report
    if not models or any(model not in ids for model in models):
        report['stop_reason'] = '请从 T0 的确切 ID 中选择待测模型'
        return report
    for model in dict.fromkeys(models):
        print(f'Probing {model}', file=sys.stderr, flush=True)
        first = probe.stream(model)
        first['pass'] = stream_ok(first) and first['content_nonempty']
        usage = probe.stream(model, stream_options={'include_usage': True})
        usage['pass'] = stream_ok(usage) and usage['usage']
        limits = []
        accepted = None
        for limit in (32768, 16384, 8192, 4096):
            attempt = probe.stream(model, first_chunk=True, max_tokens=limit)
            limits.append({'max_tokens': limit, **public(attempt)})
            if attempt['status'] == 200 and attempt.get('first_chunk_received'):
                accepted = limit
                break
            if attempt['status'] != 400:
                break  # Auth/network/rate errors do not prove a token limit.
        temperature = probe.stream(model, first_chunk=True, temperature=0.3)
        temperature['pass'] = temperature['status'] == 200 and temperature.get('first_chunk_received', False)
        tools = probe.tools(model, {})
        disabled = {}
        if not tools['pass'] or first['reasoning_content'] or first['reasoning']:
            for name, value in [('enable_thinking', False), ('thinking', {'type': 'disabled'})]:
                disabled[name] = probe.tools(model, {name: value})
        report['models'][model] = {
            'T1': public(first), 'T2': public(usage),
            'T3': {'accepted_max_tokens': accepted, 'attempts': limits},
            'T4': public(temperature), 'T5': tools, 'T6': disabled,
        }
        print(f'Completed {model}: T1={first["pass"]}, T5={tools["pass"]}', file=sys.stderr, flush=True)
    report['T7'] = probe.error(models[0])
    if not any(item['T5']['pass'] or any(value['pass'] for value in item['T6'].values())
               for item in report['models'].values()):
        report['stop_reason'] = '所有模型均未通过工具调用探测，停止接入'
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='*', help='Exact upstream IDs from T0')
    parser.add_argument('--list-only', action='store_true', help='Run T0 only')
    args = parser.parse_args()
    key = os.getenv('AUTODL_API_KEY', '').strip()
    if not key:
        print(json.dumps({'stop_reason': '缺少 AUTODL_API_KEY'}, ensure_ascii=False))
        return 2
    base = os.getenv('AUTODL_BASE_URL', DEFAULT_BASE_URL).strip().rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        print(json.dumps({'stop_reason': 'AUTODL_BASE_URL 必须为可信 HTTPS 端点'}, ensure_ascii=False))
        return 2
    with httpx.Client(timeout=httpx.Timeout(120, connect=10), follow_redirects=False) as client:
        report = run(Probe(client, base, key), args.models, list_only=args.list_only)
    # A final recursive redaction also covers upstream-provided IDs and error fragments.
    print(redact(json.dumps(report, ensure_ascii=False, indent=2), key))
    return 2 if report.get('stop_reason') else 0


if __name__ == '__main__':
    raise SystemExit(main())

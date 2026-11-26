"""Safe active checks with independent credentials and fixed probe payloads."""
import asyncio
import ipaddress
import json
import os
import re
import socket
import ssl
from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from agent_contracts.canonical import digest
from agent_contracts.management_phase2 import CheckStep, ProbeResult
from agent_app import management_catalog as catalog
from agent_app.control.metering import now_utc
from agent_app.execution.metering import model_identity, skill_identity
from agent_app.extensions.skills import (
    BUILTIN_SKILLS_DIR, VENDOR_SKILLS_DIR, _load_skill, _parse_frontmatter, _skill_directories, _vendor_config, default_store,
)
from agent_app.integrations.llm.registry import ResolvedModel
from agent_app.integrations.llm.resolver import load_registry
from agent_app.management_observations import workspace_health
from agent_app.management_workers import list_workers, revision
from datetime import timedelta

INSTANCE = uuid4().hex
OUTPUT_CAP = 32
MAX_RESPONSE = 128 * 1024
BUDGET = 1024
_probe_slot = asyncio.Semaphore(1)


class ProbeFailure(Exception):
    def __init__(self, reason, state='fail'):
        self.reason, self.state = reason, state


async def pinned_origin(url):
    endpoint = urlsplit(url)
    if endpoint.scheme != 'https' or not endpoint.hostname or endpoint.port not in (None, 443):
        raise ProbeFailure('PROBE_ENDPOINT_NOT_ALLOWED', 'unsupported')
    host = endpoint.hostname
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ProbeFailure('DNS_FAILURE') from None
    ips = [ipaddress.ip_address(record[4][0]) for record in addresses]
    if not ips or any(not ip.is_global or ip.is_multicast for ip in ips):
        raise ProbeFailure('PROBE_ADDRESS_NOT_ALLOWED', 'unsupported')
    ip = str(ips[0])
    authority = '[' + ip + ']' if ':' in ip else ip
    return 'https://' + authority + endpoint.path.rstrip('/'), host


def map_connect_error(exc):
    while exc:
        if isinstance(exc, ssl.SSLError):
            return 'TLS_FAILURE'
        if isinstance(exc, socket.gaierror):
            return 'DNS_FAILURE'
        exc = exc.__cause__ or exc.__context__
    return 'NETWORK_FAILURE'


async def request_probe(provider, profile, model=None):
    try:
        keyring = json.loads(os.getenv('AGENT_HEALTHCHECK_PROVIDER_KEYS', '{}'))
        key = keyring.get(provider.spec.id, '')
    except (ValueError, AttributeError):
        key = ''
    if not isinstance(key, str) or not key or key == provider.key.get_secret_value():
        raise ProbeFailure('DEDICATED_PROBE_CREDENTIAL_REQUIRED', 'unsupported')
    origin, host = await pinned_origin(provider.spec.base_url)
    streaming = profile == 'streaming'
    completion = model is not None and profile != 'network'
    body = None
    suffix = '/models'
    if completion:
        suffix = '/chat/completions'
        body = {'model': model.upstream_model, 'messages': [{'role': 'user', 'content': 'Reply OK.'}],
                'max_tokens': OUTPUT_CAP, 'stream': streaming}
        if profile == 'tool_calling':
            body['tools'] = [{'type': 'function', 'function': {'name': 'probe_echo', 'description': 'Probe only',
                              'parameters': {'type': 'object', 'properties': {}}}}]
            body['tool_choice'] = {'type': 'function', 'function': {'name': 'probe_echo'}}
    if body and len(json.dumps(body, ensure_ascii=False).encode('utf-8')) > BUDGET - OUTPUT_CAP:
        raise ProbeFailure('PROBE_INPUT_BUDGET_EXCEEDED', 'unsupported')
    try:
        async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False) as client:
            async with client.stream('POST' if body else 'GET', origin + suffix, json=body,
                                     extensions={'sni_hostname': host},
                                     headers={'Host': host, 'Authorization': 'Bearer ' + key}) as response:
                if response.status_code in (401, 403):
                    raise ProbeFailure('UPSTREAM_AUTH_FAILURE')
                if not response.is_success:
                    raise ProbeFailure('UPSTREAM_UNAVAILABLE')
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise ProbeFailure('PROBE_RESPONSE_LIMIT')
        if streaming:
            events = [line[5:].strip() for line in raw.decode('utf-8').splitlines() if line.startswith('data:')]
            has_delta = any(isinstance(choice, dict) and isinstance(choice.get('delta'), dict)
                            and bool(choice['delta'].get('content') or choice['delta'].get('tool_calls'))
                            for item in events if item != '[DONE]' for choice in json.loads(item).get('choices', []))
            if '[DONE]' not in events or not has_delta:
                raise ProbeFailure('STREAM_FORMAT_INVALID')
            return
        value = json.loads(raw)
        if not completion:
            if not isinstance(value.get('data'), list):
                raise ProbeFailure('UPSTREAM_FORMAT_INVALID')
            if model and not any(isinstance(item, dict) and item.get('id') == model.upstream_model
                                 for item in value['data']):
                raise ProbeFailure('UPSTREAM_MODEL_NOT_LISTED')
            return
        message = value['choices'][0]['message']
        if profile == 'tool_calling':
            if not any(item['function']['name'] == 'probe_echo' for item in message.get('tool_calls', [])):
                raise ProbeFailure('TOOL_CALLING_NOT_CONFIRMED')
        elif not isinstance(message.get('content'), str) or not message['content'].strip():
            raise ProbeFailure('COMPLETION_FORMAT_INVALID')
    except httpx.TimeoutException:
        raise ProbeFailure('NETWORK_TIMEOUT') from None
    except httpx.ConnectError as exc:
        raise ProbeFailure(map_connect_error(exc)) from None
    except httpx.HTTPError:
        raise ProbeFailure('UPSTREAM_UNAVAILABLE') from None
    except (ValueError, IndexError, KeyError, TypeError, AttributeError):
        raise ProbeFailure('UPSTREAM_FORMAT_INVALID') from None


async def provider_model(request, steps):
    try:
        registry = await asyncio.to_thread(load_registry)
    except Exception:
        raise ProbeFailure('REGISTRY_CONFIG_INVALID') from None
    model = registry.models.get(request.target_id) if request.kind == 'model' else None
    key = model.provider_id if model else request.target_id
    provider = registry.providers.get(key)
    if not provider or (request.kind == 'model' and not model):
        raise ProbeFailure('CAPABILITY_NOT_CONFIGURED')
    steps.append(CheckStep(name='configuration', state='pass'))
    if not provider.spec.enabled or (model and not model.enabled):
        raise ProbeFailure('CAPABILITY_DISABLED')
    if not provider.key.get_secret_value():
        raise ProbeFailure('CREDENTIAL_MISSING')
    steps.append(CheckStep(name='credential_presence', state='pass'))
    version = None
    if model:
        try:
            version = digest(model_identity(ResolvedModel(model, provider)).model_dump(mode='json'))
        except Exception:
            pass
    if request.profile == 'static':
        return version if model else digest(provider.spec.model_dump(mode='json'))
    if model is None and request.profile != 'network':
        raise ProbeFailure('CHECK_PROFILE_UNSUPPORTED', 'unsupported')
    if model and request.profile == 'streaming' and not model.capabilities.streaming:
        raise ProbeFailure('STREAMING_UNSUPPORTED', 'unsupported')
    if model and request.profile == 'tool_calling' and not model.capabilities.tool_calling:
        raise ProbeFailure('TOOL_CALLING_UNSUPPORTED', 'unsupported')
    await request_probe(provider, request.profile, model)
    steps.append(CheckStep(name='network_and_authentication', state='pass'))
    if request.profile != 'network':
        steps.append(CheckStep(name=request.profile, state='pass'))
    return version if model else digest(provider.spec.model_dump(mode='json'))


async def check_backend_dependency(steps):
    raw = os.getenv('BACKEND_INTERNAL_URL', '').strip()
    endpoint = urlsplit(raw)
    if endpoint.scheme not in ('https', 'http') or not endpoint.hostname or endpoint.username or endpoint.password:
        raise ProbeFailure('KNOWLEDGE_BACKEND_NOT_CONFIGURED', 'unsupported')
    configured_token = bool(os.getenv('AGENT_SERVICE_TOKEN', '').strip())
    steps.append(CheckStep(name='knowledge_credential_presence', state='pass' if configured_token else 'fail'))
    if not configured_token:
        raise ProbeFailure('KNOWLEDGE_CREDENTIAL_MISSING')
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False, follow_redirects=False) as client:
            async with client.stream('GET', endpoint.scheme + '://' + endpoint.netloc + '/api/v1/health') as response:
                if response.status_code != 200:
                    raise ProbeFailure('KNOWLEDGE_BACKEND_UNAVAILABLE')
        steps.append(CheckStep(name='knowledge_backend_liveness', state='pass'))
    except httpx.HTTPError:
        raise ProbeFailure('KNOWLEDGE_BACKEND_UNAVAILABLE') from None
    raise ProbeFailure('KNOWLEDGE_UPSTREAM_NOT_VERIFIED', 'unknown')


def tool_check(target, steps):
    item = catalog.tool_catalog().get(target)
    if not item:
        raise ProbeFailure('TOOL_CHECK_UNSUPPORTED', 'unsupported')
    steps.append(CheckStep(name='tool_parameters', state='pass' if item.schema_digest else 'unknown'))
    if target == 'tool:web_search':
        configured = bool(os.getenv('TAVILY_API_KEY', '').strip() or os.getenv('SEARXNG_BASE_URL', '').strip())
        steps.append(CheckStep(name='search_provider_configuration', state='pass' if configured else 'unknown',
                               reason=None if configured else 'SEARCH_PROVIDER_NOT_CONFIGURED'))
        if configured:
            return item.capability_version
    if target == 'tool:read_skill':
        if not default_store().names():
            raise ProbeFailure('SKILL_STORE_EMPTY')
        steps.append(CheckStep(name='skill_store', state='pass'))
        return item.capability_version
    if target in {'tool:read_file', 'tool:write_file', 'tool:edit_file', 'tool:draw_chart'}:
        result = workspace_health()
        steps.append(CheckStep(name='workspace_readability', state='pass' if result.readable == 'yes' else 'fail'))
        if result.readable != 'yes':
            raise ProbeFailure('WORKSPACE_DEPENDENCY_UNAVAILABLE')
        # Validate static dependencies without executing the business tool.
        return item.capability_version
    raise ProbeFailure('SAFE_INDEPENDENT_CHECK_UNAVAILABLE', 'unsupported')


def skill_resources(name, steps):
    if '/' in name or name in ('.', '..'):
        raise ProbeFailure('SKILL_NAME_INVALID')
    loaded = default_store().get(name)
    whitelist, vendor = _vendor_config()
    roots = [(BUILTIN_SKILLS_DIR, True)]
    if vendor:
        roots.append((VENDOR_SKILLS_DIR, False))
    if os.getenv('AGENT_EXECUTION_CONFIG_FILE') and loaded is not None:
        # default_store has already verified the pinned artifact and its root.
        roots = [(loaded.root.parent, False)]
        whitelist = ()
    for root, builtin in roots:
        if not root.is_dir():
            continue
        candidates = (path for path in _skill_directories(root) if path.name == name)
        for path in candidates:
            if not builtin and whitelist and (path.parent != root or name not in whitelist):
                continue
            if not path.resolve().is_relative_to(root.resolve()):
                raise ProbeFailure('SKILL_PATH_INVALID')
            try:
                item = _load_skill(path, builtin)
            except OSError:
                raise ProbeFailure('SKILL_RESOURCES_MISSING') from None
            except ValueError:
                raise ProbeFailure('SKILL_METADATA_OR_RESOURCE_INVALID') from None
            for label in ('frontmatter', 'resource_paths', 'resource_digest'):
                steps.append(CheckStep(name=label, state='pass'))
            if loaded is None:
                raise ProbeFailure('SKILL_NOT_LOADED')
            if loaded.resource_content_digest != item.resource_content_digest:
                raise ProbeFailure('SKILL_DIGEST_MISMATCH')
            with (path / 'SKILL.md').open(encoding='utf-8') as file:
                raw = file.read(65_537)
            if len(raw) > 65_536:
                raise ProbeFailure('SKILL_METADATA_LIMIT')
            try:
                metadata, _ = _parse_frontmatter(raw)
            except ValueError:
                raise ProbeFailure('SKILL_METADATA_OR_RESOURCE_INVALID') from None
            for label in ('references', 'scripts'):
                declared = metadata.get(label)
                if declared is None:
                    steps.append(CheckStep(name=label, state='unknown', reason='DECLARATION_NOT_PROVIDED'))
                    continue
                if (not isinstance(declared, list) or len(declared) > 100 or
                        any(not isinstance(name, str) or not name or '\\' in name or
                            any(part in ('', '.', '..') for part in name.split('/')) for name in declared)):
                    raise ProbeFailure('SKILL_RESOURCE_DECLARATION_INVALID')
                base = (Path(path) / label).resolve()
                for name in declared:
                    candidate = base / name
                    if not candidate.resolve().is_relative_to(base) or not candidate.is_file():
                        raise ProbeFailure('SKILL_DECLARED_RESOURCE_MISSING')
                steps.append(CheckStep(name=label, state='pass'))
            dependencies = metadata.get('dependencies')
            if dependencies is None:
                steps.append(CheckStep(name='declared_dependencies', state='unknown', reason='DECLARATION_NOT_PROVIDED'))
            else:
                if (not isinstance(dependencies, list) or len(dependencies) > 40 or
                        any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', name)
                            for name in dependencies)):
                    raise ProbeFailure('SKILL_DEPENDENCY_DECLARATION_UNSUPPORTED', 'unsupported')
                try:
                    for name in dependencies:
                        installed_version(name)
                except PackageNotFoundError:
                    raise ProbeFailure('SKILL_DEPENDENCY_UNAVAILABLE') from None
                steps.append(CheckStep(name='declared_dependencies', state='pass'))
            return item.resource_content_digest
    raise ProbeFailure('SKILL_RESOURCES_MISSING')


async def skill_check(target, steps):
    version = await asyncio.to_thread(skill_resources, target, steps)
    try:
        workers = await list_workers(0, 100, include_manifest=True)
    except Exception:
        workers = []
    identity_version = digest(skill_identity(default_store().get(target)).model_dump(mode='json'))
    installed = [(item.id, item.version) for worker in workers if worker.state == 'online' and worker.manifest
                 for item in worker.manifest.capabilities
                 if item.kind == 'skill' and item.id in (target, 'skill:' + target)]
    if any(item_version != (identity_version if item_id.startswith('skill:') else version)
           for item_id, item_version in installed):
        steps.append(CheckStep(name='worker_version_agreement', state='fail', reason='WORKER_SKILL_VERSION_MISMATCH'))
        raise ProbeFailure('WORKER_SKILL_VERSION_MISMATCH')
    steps.append(CheckStep(name='worker_version_agreement', state='pass' if installed else 'unknown',
                           reason=None if installed else 'NO_FRESH_WORKER_EVIDENCE'))
    return version


async def check(request):
    started = perf_counter()
    observed = now_utc()
    steps = []
    state, reason, version = 'pass', 'CHECK_PASSED', None
    budget = BUDGET if request.kind == 'model' and request.profile in ('completion', 'streaming', 'tool_calling') else 0
    try:
        if _probe_slot.locked():
            raise ProbeFailure('PROBE_BUSY', 'unknown')
        async with _probe_slot, asyncio.timeout(7):
            if request.kind in ('provider', 'model'):
                version = await provider_model(request, steps)
            elif request.profile != 'static':
                raise ProbeFailure('CHECK_PROFILE_UNSUPPORTED', 'unsupported')
            elif request.kind == 'tool':
                if request.target_id in {'tool:paper_search', 'tool:paper_detail', 'tool:citation_graph', 'tool:read_paper'}:
                    await check_backend_dependency(steps)
                else:
                    version = await asyncio.to_thread(tool_check, request.target_id, steps)
            else:
                version = await skill_check(request.target_id, steps)
    except TimeoutError:
        state, reason = 'fail', 'CHECK_TIMEOUT'
    except ProbeFailure as exc:
        state, reason = exc.state, exc.reason
    except Exception:
        state, reason = 'unknown', 'CHECK_EVIDENCE_UNAVAILABLE'
    return ProbeResult(kind=request.kind, target_id=request.target_id, profile=request.profile, state=state, reason=reason,
                       observed_at=observed, expires_at=observed + timedelta(minutes=5), instance_id=INSTANCE,
                       duration_ms=int((perf_counter() - started) * 1000), build_revision=revision('AGENT_BUILD_REVISION'),
                       config_revision=revision('AGENT_CONFIG_REVISION') or revision(
                           'AGENT_TOOL_CONFIGURATION_RELEASE' if request.kind == 'tool' else 'AGENT_MODEL_ROUTE_REVISION'),
                        capability_version=version, budget_tokens=budget, steps=steps,
                        coverage='partial' if any(step.state in ('unknown', 'unsupported') for step in steps)
                        else 'complete' if state == 'pass' else 'unknown')

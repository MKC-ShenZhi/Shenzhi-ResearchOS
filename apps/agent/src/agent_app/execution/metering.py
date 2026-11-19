"""Injected Worker adapter at real execution boundaries, shared by parallel tools.

No entitlements live here. Every v2 call waits for a durable Control start and
uses its receipt once; replay never restores permission to send.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import uuid
import json
import httpx

from agent_contracts.canonical import digest, request_digest_v1
from agent_contracts.v2 import ModelIdentity, SkillIdentity, ToolIdentity
from agent_app.errors import BusinessError

current_meter: ContextVar['WorkerMeter | None'] = ContextVar('agent_execution_meter', default=None)
current_parent_call: ContextVar[str | None] = ContextVar('agent_parent_call', default=None)


def _bytes_digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def controlled_resource_digest(root: Path):
    root = root.resolve()
    files = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if any(part in ('__pycache__', '.git', '.venv') for part in relative.parts):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('controlled resources cannot contain symlinks')
        if path.is_file():
            files.append([relative.as_posix(), _bytes_digest(path.read_bytes())])
    if not files:
        raise ValueError('controlled resource set is empty')
    return digest(files)


def implementation_digest():
    # Full controlled Python implementation plus dependency lock; no runtime env,
    # mtime, absolute path, endpoint or credentials enter exported identity.
    source = Path(__file__).resolve().parents[1]
    build = [[p.relative_to(source).as_posix(), _bytes_digest(p.read_bytes())]
             for p in sorted(source.rglob('*.py'))]
    lock = source.parents[1] / 'uv.lock'
    if not lock.is_file():
        raise ValueError('dependency lock missing')
    return digest({'files': build, 'dependency_lock': _bytes_digest(lock.read_bytes())})


def tool_identity(target):
    configuration_release = os.getenv('AGENT_TOOL_CONFIGURATION_RELEASE', '').strip()
    if not configuration_release:
        raise BusinessError(20004, '工具非敏感配置修订未配置，拒绝计量执行', 503)
    return ToolIdentity(schema_version=1, kind='tool', capability_id='tool:' + target.spec.name,
        implementation_build_digest=implementation_digest(),
        parameter_schema_digest=request_digest_v1(target.spec.parameters),
        dependency_digests=[digest({'configuration_release': configuration_release})])


def skill_identity(skill):
    resource_digest = controlled_resource_digest(skill.root)
    loaded_digest = getattr(skill, 'resource_content_digest', None)
    if loaded_digest is not None and loaded_digest != resource_digest:
        raise BusinessError(20004, '技能资源与装载版本不一致', 403)
    return SkillIdentity(schema_version=1, kind='skill', capability_id='skill:' + skill.name,
                         resource_content_digest=resource_digest, dependency_digests=[])


def model_identity(resolved):
    route_revision = os.getenv('AGENT_MODEL_ROUTE_REVISION', '').strip()
    if not route_revision:
        raise BusinessError(20004, '模型非敏感路由修订未配置，拒绝计量执行', 503)
    return ModelIdentity(schema_version=1, kind='model', capability_id='model:' + resolved.spec.id,
        provider_id=resolved.provider.spec.id, registry_model_id=resolved.spec.id,
        upstream_model=resolved.upstream_model, configuration_release_digest=digest({
            'protocol': resolved.provider.spec.protocol,
            'capabilities': resolved.spec.capabilities.model_dump(mode='json'),
            'request_params': resolved.spec.request_params,
            'route_revision': route_revision,
            'thinking_disabled': os.getenv('AGENT_DISABLE_THINKING', '').strip().lower() == 'true',
            'adapter_build': implementation_digest(), 'usage_frame_semantics': 'cumulative'}), dependency_digests=[])


class Measurement:
    def __init__(self, *, is_model=True):
        self.prompt_tokens = self.completion_tokens = None
        self.provider_request_id = None
        self.outcome = 'failed'
        self.successful_units = None
        self.is_model = is_model
        self.inconsistent = False
        self.complete_snapshot = False
        self.send_guard = None

    def ensure_send(self):
        if self.send_guard is not None:
            self.send_guard()

    def cumulative_usage(self, raw):
        self.complete_snapshot = all(type(raw.get(k)) is int and raw[k] >= 0
                                     for k in ('prompt_tokens', 'completion_tokens'))
        for name in ('prompt_tokens', 'completion_tokens'):
            value = raw.get(name)
            if type(value) is not int or value < 0:
                continue
            prior = getattr(self, name)
            if prior is not None and value < prior:
                self.inconsistent = True
            setattr(self, name, value)

    def observation(self):
        known = sum(v is not None for v in (self.prompt_tokens, self.completion_tokens))
        if self.inconsistent:
            # Contradictory cumulative frames need evidence reconciliation.
            self.prompt_tokens = self.completion_tokens = None
            known = 0
        return dict(outcome=self.outcome, prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens,
                    usage_status=('measured' if known == 2 and self.complete_snapshot else 'partial' if known else 'unknown') if self.is_model else 'measured',
                    usage_source='provider_usage' if self.is_model and known else None if self.is_model else 'not_applicable',
                    missing_reason=('conflicting_usage_frames' if self.inconsistent else 'incomplete_final_usage' if known else 'no_usage')
                        if self.is_model and (known < 2 or not self.complete_snapshot) else None,
                    attempted_units=1, successful_units=self.successful_units, provider_request_id=self.provider_request_id,
                    ended_at=datetime.now(timezone.utc).isoformat())


class WorkerMeter:
    def __init__(self, control, *, run_id, execution_id, worker_id, lease_token, context, stop,
                 risk_profile=None):
        self.control, self.run_id, self.context, self.stop = control, run_id, context, stop
        self.worker = dict(schema_version=1, execution_id=execution_id, worker_id=worker_id, lease_token=lease_token)
        self.risk_profile = risk_profile
        self.receipts = {}
        spool_root = os.getenv('AGENT_USAGE_SPOOL_ROOT', '').strip()
        if not spool_root:
            raise BusinessError(20004, 'Worker 持久用量目录未配置', 503)
        self.spool_root = Path(spool_root).resolve()
        self.spool_root.mkdir(parents=True, exist_ok=True)

    async def begin(self, identity, *, purpose, invocation='internal', logical_id=None, request_digest=None,
                    logical_attempt=1, transport_attempt=1, activation_id=None):
        if self.stop.is_set():
            raise asyncio.CancelledError()
        call_id = uuid.uuid4().hex
        payload = dict(self.worker, call_id=call_id, logical_call_id=logical_id or call_id,
                       capability_identity=identity.model_dump(mode='json'), invocation_mode=invocation,
                       purpose=purpose, parent_call_id=current_parent_call.get(), activation_id=activation_id,
                       logical_attempt=logical_attempt, transport_attempt=transport_attempt,
                       provider_id=identity.provider_id if identity.kind == 'model' else None,
                       request_digest=request_digest or digest([identity.capability_id, purpose]),
                       input_bound_evidence_ref=None, output_bound_evidence_ref=None, risk_profile=self.risk_profile)
        path = 'calls/authorize' if self.context == 'authorized' else 'call-intents'
        try:
            intent = await self.control.post(f'/internal/v2/runs/{self.run_id}/{path}', payload)
            if intent.get('activation_already_recorded'):
                return None
            start = await self.control.post(f'/internal/v2/calls/{call_id}/start', self.worker)
        except Exception as exc:
            self.stop.set()
            # A Control timeout is not a provider failure and must never enter
            # the provider's HTTP retry loop or create a second sending right.
            raise BusinessError(20004, '调用授权或启动未获可信回执', 503) from exc
        if not start.get('may_send'):
            self.stop.set()
            raise BusinessError(20004, '调用已经启动，禁止重复发送', 409)
        cutoff = start.get('start_before')
        if self.stop.is_set() or (cutoff and datetime.now(timezone.utc) >= datetime.fromisoformat(cutoff)):
            self.stop.set()
            raise BusinessError(20004, '调用启动截止或执行权失效', 403)
        self.receipts[call_id] = [cutoff, False]
        return call_id

    def consume_send(self, call_id):
        cutoff, used = self.receipts[call_id]
        if used or self.stop.is_set() or (cutoff and datetime.now(timezone.utc) >= datetime.fromisoformat(cutoff)):
            self.stop.set()
            raise BusinessError(20004, '调用发送许可已使用或截止', 403)
        self.receipts[call_id][1] = True

    async def complete(self, call_id, measurement):
        if call_id is None:
            return
        # Stable submission ID across response loss and retransmission.
        body = dict(self.worker, observation_submission_id=uuid.uuid4().hex, call_id=call_id,
                    **measurement.observation())
        spool = self.spool_root / (body['observation_submission_id'] + '.json')
        temporary = spool.with_suffix('.tmp')
        with temporary.open('xb') as stream:
            stream.write(json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(spool)
        error = None
        for attempt in range(3):
            try:
                await self.control.post('/internal/v2/usage-observations', body)
                spool.unlink(missing_ok=True)
                return
            except Exception as exc:
                error = exc
                if attempt < 2:
                    await asyncio.sleep(0.1 * 2**attempt)
        # Durable started fact still exists; stop further calls rather than lose
        # accounting silently. Recovery exposes unknown if completion is lost.
        self.stop.set()
        raise BusinessError(20004, '调用观察未获持久回执，停止新增调用', 503) from error


    async def activate(self, skill, invocation='model_selected'):
        call_id = await self.begin(skill_identity(skill), purpose='skill_activation', invocation=invocation,
                                   activation_id=uuid.uuid4().hex)
        if call_id is not None:
            self.consume_send(call_id)
        measurement = Measurement(is_model=False)
        measurement.outcome, measurement.successful_units = 'succeeded', 1
        await self.complete(call_id, measurement)


async def replay_observation_spool(control):
    root = os.getenv('AGENT_USAGE_SPOOL_ROOT', '').strip()
    if not root:
        raise BusinessError(20004, 'Worker 持久用量目录未配置', 503)
    for path in sorted(Path(root).glob('*.json')):
        body = json.loads(path.read_text(encoding='utf-8'))
        await control.post('/internal/v2/usage-observations', body)
        path.unlink(missing_ok=True)


@asynccontextmanager
async def actual_call(identity_factory, *, purpose, logical_id=None, request_digest=None,
                      logical_attempt=1, transport_attempt=1, invocation='internal'):
    meter = current_meter.get()
    measurement = Measurement()
    if meter is None:
        yield measurement
        return
    identity = identity_factory()
    measurement.is_model = identity.kind == 'model'
    call_id = await meter.begin(identity, purpose=purpose, logical_id=logical_id,
                               request_digest=request_digest, logical_attempt=logical_attempt,
                               transport_attempt=transport_attempt, invocation=invocation)
    if hasattr(meter, 'consume_send'):
        measurement.send_guard = lambda: meter.consume_send(call_id)
    token = current_parent_call.set(call_id)
    try:
        yield measurement
    except asyncio.CancelledError:
        measurement.outcome = 'cancelled'
        raise
    except (TimeoutError, httpx.TimeoutException):
        measurement.outcome = 'timed_out'
        raise
    finally:
        current_parent_call.reset(token)
        await meter.complete(call_id, measurement)

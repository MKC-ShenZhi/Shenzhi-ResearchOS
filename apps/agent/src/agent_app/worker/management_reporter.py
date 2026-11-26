"""Independently reports Worker evidence using a worker-specific credential."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from uuid import uuid4

import httpx

from agent_contracts.canonical import digest
from agent_contracts.management_phase2 import Capability, WorkerManifest, WorkerReport
from agent_app import management_catalog as catalog
from agent_app.management_workers import revision, setting

log = logging.getLogger(__name__)
_current_reporter = ContextVar('management_reporter', default=None)


def record_runtime(runtime):
    reporter = _current_reporter.get()
    if reporter is None:
        return
    registry = getattr(runtime, 'registry', None)
    if registry is not None:
        reporter.registry = registry


def runtime_version():
    try:
        return version('shenzhi-agent')
    except PackageNotFoundError:
        return 'unknown'


def manifest():
    providers, models = catalog.llm_catalog()
    tools = catalog.tool_catalog()
    skills = catalog.skill_catalog()
    facts = [Capability(kind='provider', id=item.provider_id, scope='loaded') for item in providers.values()]
    facts.extend(Capability(kind='model', id=item.model_id, version=item.capability_version, scope='loaded')
                 for item in models.values())
    facts.extend(Capability(kind='tool', id=item.tool_id, version=item.capability_version,
                            scope=item.registration, conditions=item.conditions) for item in tools.values())
    facts.extend(Capability(kind='skill', id=item.name, version=item.resource_digest, scope='loaded')
                 for item in skills.values() if item.integrity == 'yes')
    registry = [
        {'id': item.model_id, 'provider': item.provider_id, 'version': item.capability_version,
         'enabled': item.enabled, 'configured': item.states.configured.state, 'defaults': item.default_purposes}
        for item in sorted(models.values(), key=lambda item: item.model_id)
    ]
    profile = None
    if os.getenv('AGENT_EXECUTION_CONFIG_FILE'):
        from agent_app.execution.config_profile import load_profile, config_error
        from agent_app.execution.metering import implementation_digest, skill_identity
        from agent_app.extensions.skills import default_store
        profile = load_profile()
        if runtime_version() != profile[1].runtime_version:
            raise config_error()
        spec = profile[1]
        requested = {tool.id: tool for tool in spec.tools}
        binary = implementation_digest() if requested else None
        if any(not tools.get(key) or tools[key].capability_version != item.digest
               or item.implementation_digest != binary for key, item in requested.items()):
            raise config_error()
        store = default_store()
        facts = [fact for fact in facts if fact.kind != 'skill' and
                 (fact.kind != 'tool' or fact.id in requested) and
                 (fact.kind != 'model' or models[fact.id].states.configured.state == 'yes')]
        facts.extend(Capability(kind='skill', id='skill:' + name, scope='loaded',
                                version=digest(skill_identity(store.get(name)).model_dump(mode='json')))
                     for name in store.names())
    return WorkerManifest(build_revision=revision('AGENT_BUILD_REVISION'),
                          config_revision=profile[0] if profile else (
                              revision('AGENT_CONFIG_REVISION') or revision('AGENT_MODEL_ROUTE_REVISION')),
                          config_digest=profile[1].config_digest if profile else None,
                          runtime_version=runtime_version(), registry_digest=digest(registry),
                          capabilities=sorted(facts, key=lambda item: (item.kind, item.id))[:512])


class Reporter:
    def __init__(self, worker_id, client):
        self.worker_id, self.client = worker_id, client
        self.instance_id = uuid4()
        self.started = datetime.now(timezone.utc)
        self.sequence = 0
        self.acknowledged = None
        self.run_id = None
        self.registry = None
        self.previous = None

    async def send(self, offline=False):
        health = 'unknown'
        payload = self.previous
        if not offline:
            try:
                async with asyncio.timeout(3):
                    payload = await asyncio.to_thread(manifest)
                self.previous = payload
                health = 'ok'
            except Exception:
                # Do not log configurations, paths or provider details.
                health = 'degraded'
        key = digest(payload.model_dump(mode='json')) if payload else None
        self.sequence += 1
        report = WorkerReport(
            instance_id=self.instance_id, sequence=self.sequence, started_at=self.started,
            lifecycle='offline' if offline else 'running', health=health,
            active_run_id=None if offline else self.run_id, manifest_digest=key,
            run_tool_ids=['tool:' + name for name in self.registry.enabled()[:200]]
            if not offline and self.run_id and self.registry else [],
            run_latent_tool_ids=['tool:' + name for name in sorted(self.registry.latent)[:200]]
            if not offline and self.run_id and self.registry else None,
            run_tools_complete=(len(self.registry.enabled()) <= 200 and len(self.registry.latent) <= 200)
            if not offline and self.run_id and self.registry else None,
            manifest=payload if key != self.acknowledged else None,
        )
        try:
            response = await self.client.put(
                f'/internal/v2/worker-reports/{self.worker_id}', json=report.model_dump(mode='json'))
            response.raise_for_status()
            self.acknowledged = None if response.json()['data']['want_manifest'] else key
            return True
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            log.debug('Worker management heartbeat unavailable')
            return False

    async def run(self):
        period = setting('AGENT_WORKER_REPORT_INTERVAL_SECONDS', 15, 2, 600)
        while True:
            try:
                await self.send()
            except Exception:
                log.debug('Worker management heartbeat projection unavailable')
            await asyncio.sleep(period)


@asynccontextmanager
async def reports(worker_id):
    token = os.getenv('AGENT_WORKER_REPORT_TOKEN', '').strip()
    if not token or '/' in worker_id or os.getenv('AGENT_CONFIG_WORKER_ROLE') == 'candidate':
        yield None
        return
    async with httpx.AsyncClient(base_url=os.getenv('AGENT_INTERNAL_URL', 'http://127.0.0.1:8101'),
                                 headers={'Authorization': 'Bearer ' + token},
                                 timeout=2, trust_env=False) as client:
        reporter = Reporter(worker_id, client)
        task = asyncio.create_task(reporter.run(), name='agent-management-reporter')
        context = _current_reporter.set(reporter)
        try:
            yield reporter
        finally:
            _current_reporter.reset(context)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            try:
                async with asyncio.timeout(2.5):
                    await reporter.send(offline=True)
            except Exception:
                log.debug('Worker management offline report unavailable')

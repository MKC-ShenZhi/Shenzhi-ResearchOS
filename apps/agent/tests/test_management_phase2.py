"""Phase 2 Worker, probe and audit tests without production services."""
import asyncio
import hashlib
import json
import os
import socket
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from types import SimpleNamespace

import httpx

from agent_contracts.canonical import digest
from agent_contracts.management_phase2 import Capability, ProbeRequest, WorkerManifest, WorkerReport
from agent_app import management_checks as checks, management_workers
from agent_app.control.metering import now_utc
from agent_app.infrastructure.management_models import WorkerSnapshotRow
from agent_app.worker.management_reporter import Reporter, reports
from tests.test_management import ENV, MODEL, ManagementFixture
from tests import test_management_bridge as bridge_module
from tests.test_management_bridge import ADMIN, ROOT

REPORT_TOKEN = 'worker-specific-test-token-with-32-chars'
AUDIT_SECRET = 'another-independent-audit-secret-for-tests'
PHASE2 = {
    'AGENT_WORKER_REPORT_IDENTITIES': json.dumps({'worker-a': hashlib.sha256(REPORT_TOKEN.encode()).hexdigest()}),
    'ADMIN_AGENT_AUDIT_SECRET': AUDIT_SECRET, 'ADMIN_AGENT_DIAGNOSTICS': 'true',
}
PREFIX = '/internal/v2'


class WorkerEvidenceTests(ManagementFixture):
    async def test_report_identity_idempotency_version_offline_and_stale(self):
        started = now_utc() - timedelta(seconds=1)
        instance = uuid4()
        first = WorkerManifest(runtime_version='test', config_revision='v1', capabilities=[])
        report = WorkerReport(instance_id=instance, sequence=1, started_at=started, lifecycle='running',
                              health='ok', manifest=first, manifest_digest=digest(first.model_dump(mode='json')))
        headers = {'Authorization': 'Bearer ' + REPORT_TOKEN}
        with patch.dict(os.environ, PHASE2):
            url = PREFIX + '/worker-reports/worker-a'
            forged = await self.client.put(PREFIX + '/worker-reports/worker-b', headers=headers,
                                           json=report.model_dump(mode='json'))
            self.assertEqual(forged.status_code, 403)
            legacy = await self.client.put(url, headers={'Authorization': 'Bearer ' + ENV['AGENT_WORKER_TOKEN']},
                                           json=report.model_dump(mode='json'))
            self.assertEqual(legacy.status_code, 403)
            denied = await self.client.get(PREFIX + '/management/worker-evidence', headers=headers)
            self.assertEqual(denied.status_code, 403)
            r1 = await self.client.put(url, headers=headers, json=report.model_dump(mode='json'))
            self.assertEqual(r1.status_code, 200, r1.text)
            replay = await self.client.put(url, headers=headers, json=report.model_dump(mode='json'))
            self.assertEqual(r1.json(), replay.json())
            different = report.model_copy(update={'health': 'degraded'})
            rejected = await self.client.put(url, headers=headers, json=different.model_dump(mode='json'))
            self.assertEqual(rejected.status_code, 409)
            next_manifest = first.model_copy(update={'config_revision': 'v2'})
            upgrade = report.model_copy(update={'manifest': next_manifest, 'sequence': 2,
                                                 'manifest_digest': digest(next_manifest.model_dump(mode='json'))})
            self.assertEqual((await self.client.put(url, headers=headers, json=upgrade.model_dump(mode='json'))).status_code, 200)
            observer = {'Authorization': 'Bearer ' + ENV['AGENT_MANAGEMENT_TOKEN']}
            endpoint = PREFIX + '/management/worker-evidence/worker-a'
            result = await self.client.get(endpoint, headers=observer)
            self.assertEqual(result.json()['data']['manifest']['config_revision'], 'v2')
            self.assertNotIn(REPORT_TOKEN, result.text)
            async with self.db.begin() as db:
                row = await db.get(WorkerSnapshotRow, 'worker-a')
                row.observed_at = now_utc() - timedelta(seconds=60)
            self.assertEqual((await self.client.get(endpoint, headers=observer)).json()['data']['state'], 'stale')
            async with self.db.begin() as db:
                row = await db.get(WorkerSnapshotRow, 'worker-a')
                row.observed_at = now_utc() - timedelta(seconds=120)
            self.assertEqual((await self.client.get(endpoint, headers=observer)).json()['data']['state'], 'offline')
            end = upgrade.model_copy(update={'sequence': 3, 'lifecycle': 'offline'})
            self.assertEqual((await self.client.put(url, headers=headers, json=end.model_dump(mode='json'))).status_code, 200)
            self.assertEqual((await self.client.get(endpoint, headers=observer)).json()['data']['state'], 'offline')

    async def test_worker_report_transport_retries_and_reports_manifest_changes(self):
        received = []

        async def handler(request):
            received.append(json.loads(request.content))
            if len(received) == 1:
                raise httpx.ConnectError('test transport down')
            return httpx.Response(200, json={'data': {'want_manifest': False}})

        with patch('agent_app.worker.management_reporter.manifest', side_effect=[
            WorkerManifest(runtime_version='test', config_revision='v1', capabilities=[]),
            WorkerManifest(runtime_version='test', config_revision='v1', capabilities=[]),
            WorkerManifest(runtime_version='test', config_revision='v2', capabilities=[]),
        ]):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://127.0.0.1') as client:
                reporter = Reporter('worker-a', client)
                self.assertFalse(await reporter.send())
                self.assertTrue(await reporter.send())
                self.assertTrue(await reporter.send())
                self.assertTrue(await reporter.send(offline=True))
        self.assertEqual([entry['sequence'] for entry in received], [1, 2, 3, 4])
        self.assertEqual(received[1]['manifest']['config_revision'], 'v1')
        self.assertEqual(received[2]['manifest']['config_revision'], 'v2')
        self.assertIsNone(received[3]['manifest'])
        self.assertEqual(received[3]['lifecycle'], 'offline')

    async def test_start_and_graceful_exit_report(self):
        started = asyncio.Event()

        async def send(_reporter, offline=False):
            if not offline:
                started.set()
            return True

        create = httpx.AsyncClient
        transport = httpx.MockTransport(lambda _: httpx.Response(200))
        with patch.dict(os.environ, {'AGENT_WORKER_REPORT_TOKEN': REPORT_TOKEN}), patch.object(
            httpx, 'AsyncClient', side_effect=lambda **kw: create(transport=transport, **kw),
        ), patch.object(Reporter, 'send', autospec=True, side_effect=send) as observed:
            async with reports('worker-a'):
                await asyncio.wait_for(started.wait(), 1)
        self.assertTrue(observed.await_args.kwargs['offline'])


class ProbeTests(ManagementFixture):
    async def test_pinned_skill_checks_and_legacy_worker_evidence(self):
        name = 'phase2-artifact'
        with TemporaryDirectory() as directory:
            folder = Path(directory) / name
            folder.mkdir()
            document = folder / 'SKILL.md'
            document.write_text('---\nname: phase2-artifact\ndescription: Artifact fixture\n---\nbody', encoding='utf-8')
            loaded = checks._load_skill(folder, False)
            identity = digest(checks.skill_identity(loaded).model_dump(mode='json'))
            worker = SimpleNamespace(worker_id='worker-a', state='online', observed_at=now_utc(),
                manifest_digest=None, manifest=WorkerManifest(runtime_version='test', capabilities=[
                    Capability(kind='skill', id='skill:' + name, version=identity, scope='loaded')]))
            with patch.dict(os.environ, {'AGENT_EXECUTION_CONFIG_FILE': 'fixture'}), \
                    patch.object(checks, 'default_store', return_value={name: loaded}), \
                    patch.object(checks, 'list_workers', AsyncMock(return_value=[worker])), \
                    patch.object(management_workers, 'list_workers', AsyncMock(return_value=[worker])):
                result = await checks.check(ProbeRequest(kind='skill', target_id=name))
                self.assertEqual(result.state, 'pass', result.reason)
                for query in (name, 'skill:' + name):
                    evidence = await management_workers.capability_evidence('skill', query, 0, 10)
                    self.assertIsNotNone(evidence[0].capability)
                worker.manifest.capabilities[0] = Capability(kind='skill', id=name,
                    version=loaded.resource_content_digest, scope='loaded')
                self.assertEqual((await checks.check(ProbeRequest(kind='skill', target_id=name))).state, 'pass')
                worker.manifest.capabilities[0] = Capability(kind='skill', id='skill:' + name,
                    version=digest('wrong-version'), scope='loaded')
                result = await checks.check(ProbeRequest(kind='skill', target_id=name))
                self.assertEqual(result.reason, 'WORKER_SKILL_VERSION_MISMATCH')
                document.write_text(document.read_text(encoding='utf-8') + 'changed', encoding='utf-8')
                result = await checks.check(ProbeRequest(kind='skill', target_id=name))
                self.assertEqual(result.reason, 'SKILL_DIGEST_MISMATCH')

    async def test_fixed_payload_and_no_secret_leak(self):
        requests = []
        transport = httpx.MockTransport(lambda request: (
            requests.append(request) or httpx.Response(
                200, json={'choices': [{'message': {'content': 'OK'}}], 'private': 'do-not-project'})))
        create = httpx.AsyncClient
        request = ProbeRequest(kind='model', target_id=MODEL, profile='completion')
        with patch.dict(os.environ, {'AGENT_HEALTHCHECK_PROVIDER_KEYS': '{"deepseek":"test-dedicated-probe-key"}'}), patch.object(
            checks, 'pinned_origin', new=AsyncMock(return_value=('https://203.0.113.5/v1', 'example.invalid'))
        ), patch.object(checks.httpx, 'AsyncClient', side_effect=lambda **kwargs: create(transport=transport, **kwargs)):
            result = await checks.check(request)
        self.assertEqual(result.state, 'pass')
        self.assertEqual(result.budget_tokens, checks.BUDGET)
        self.assertEqual(json.loads(requests[0].content)['max_tokens'], checks.OUTPUT_CAP)
        self.assertNotIn('test-dedicated-probe-key', result.model_dump_json())
        self.assertNotIn('do-not-project', result.model_dump_json())

    async def test_provider_failures_and_busy(self):
        static = ProbeRequest(kind='provider', target_id='deepseek')
        self.assertEqual((await checks.check(static)).state, 'pass')
        self.assertEqual((await checks.check(static.model_copy(update={'target_id': 'absent'}))).reason,
                         'CAPABILITY_NOT_CONFIGURED')
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}):
            self.assertEqual((await checks.check(static)).reason, 'CREDENTIAL_MISSING')
        with patch.object(asyncio.get_running_loop(), 'getaddrinfo', new=AsyncMock(side_effect=socket.gaierror)):
            with self.assertRaisesRegex(checks.ProbeFailure, 'DNS_FAILURE'):
                await checks.pinned_origin('https://example.invalid')
        async with checks._probe_slot:
            self.assertEqual((await checks.check(static)).reason, 'PROBE_BUSY')
        create = httpx.AsyncClient
        for value, expected in ((httpx.Response(401), 'UPSTREAM_AUTH_FAILURE'),
                                (httpx.Response(502), 'UPSTREAM_UNAVAILABLE'),
                                (httpx.ReadTimeout('test'), 'NETWORK_TIMEOUT')):
            def reply(request):
                if isinstance(value, Exception):
                    raise value
                return value

            with patch.dict(os.environ, {'AGENT_HEALTHCHECK_PROVIDER_KEYS': '{"deepseek":"test-probe-key"}'}), patch.object(
                checks, 'pinned_origin', new=AsyncMock(return_value=('https://203.0.113.5', 'example.invalid'))
            ), patch.object(checks.httpx, 'AsyncClient',
                            side_effect=lambda **kwargs: create(transport=httpx.MockTransport(reply), **kwargs)):
                result = await checks.check(static.model_copy(update={'profile': 'network'}))
            self.assertEqual(result.reason, expected)

    async def test_tools_do_not_execute_and_error_is_structured(self):
        request = ProbeRequest(kind='tool', target_id='tool:web_search')
        with patch('agent_app.execution.tools.FunctionTool.execute', side_effect=AssertionError):
            self.assertEqual((await checks.check(request)).state, 'unsupported')
        with patch.dict(os.environ, {'BACKEND_INTERNAL_URL': 'http://127.0.0.1:8000', 'AGENT_SERVICE_TOKEN': ''}):
            failure = await checks.check(request.model_copy(update={'target_id': 'tool:paper_search'}))
        self.assertEqual(failure.reason, 'KNOWLEDGE_CREDENTIAL_MISSING')

    async def test_skill_missing_frontmatter_and_digest_drift(self):
        request = ProbeRequest(kind='skill', target_id='phase2-skill')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / 'phase2-skill'
            skill.mkdir()
            md = skill / 'SKILL.md'
            with patch.object(checks, 'BUILTIN_SKILLS_DIR', root), patch.object(checks, 'VENDOR_SKILLS_DIR', root / 'absent'):
                self.assertEqual((await checks.check(request)).reason, 'SKILL_RESOURCES_MISSING')
                md.write_text('bad frontmatter', encoding='utf-8')
                self.assertEqual((await checks.check(request)).reason, 'SKILL_METADATA_OR_RESOURCE_INVALID')
                md.write_text('---\nname: phase2-skill\ndescription: Test Skill\n---\nbody', encoding='utf-8')
                with patch.object(checks, 'default_store', return_value={'phase2-skill': type('Loaded', (), {
                    'resource_content_digest': 'old-digest'})()}):
                    self.assertEqual((await checks.check(request)).reason, 'SKILL_DIGEST_MISMATCH')
                self.assertEqual((await checks.check(request.model_copy(update={'target_id': 'x/../y'}))).reason,
                                 'SKILL_NAME_INVALID')
                md.write_text('---\nname: phase2-skill\ndescription: Test Skill\nreferences: [missing.md]\n---\nbody', encoding='utf-8')
                loaded = checks._load_skill(skill, True)
                with patch.object(checks, 'default_store', return_value={'phase2-skill': loaded}):
                    self.assertEqual((await checks.check(request)).reason, 'SKILL_DECLARED_RESOURCE_MISSING')


# The existing bridge covers both Admin and Agent authentication. Add only the Phase 2 Model/table to that fixture.
from app.api.agent_management_phase2 import router as phase2_router
from app.models.agent_management import ManagementAuditRow
from app.models.agent_entitlements import EntitlementAuditRow
from app.services import agent_management_audit as audit
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


class ManagementAuditTests(bridge_module.ManagementBridgeTests):
    phase2_browser = True

    async def asyncSetUp(self):
        await super().asyncSetUp()
        config = patch.dict(os.environ, PHASE2)
        config.start()
        self.addCleanup(config.stop)
        async with self.backend_engine.begin() as connection:
            await connection.run_sync(ManagementAuditRow.__table__.create)
            await connection.run_sync(EntitlementAuditRow.__table__.create)
        self.backend_app.include_router(phase2_router)
        from app.api.agent_config_management import router as config_router
        self.backend_app.include_router(config_router)
        config_role = patch.dict(os.environ, {'AGENT_CONFIG_MANAGEMENT_TOKEN': 'fixture-config-service-credential'})
        config_role.start()
        self.addCleanup(config_role.stop)
        self.audit_db = async_sessionmaker(self.backend_engine, expire_on_commit=False)
        factory = patch.object(audit, 'get_session_factory', return_value=self.audit_db)
        factory.start()
        self.addCleanup(factory.stop)
        data = WorkerManifest(runtime_version='test', config_revision='phase2-browser-config', capabilities=[])
        report = WorkerReport(instance_id=uuid4(), sequence=1, started_at=now_utc(), lifecycle='running',
                              health='ok', manifest=data, manifest_digest=digest(data.model_dump(mode='json')))
        response = await self.client.put(PREFIX + '/worker-reports/worker-a',
                                         headers={'Authorization': 'Bearer ' + REPORT_TOKEN},
                                         json=report.model_dump(mode='json'))
        self.assertEqual(response.status_code, 200, response.text)

    async def login(self):
        await self.browser.post(ROOT + '/auth/login', json={
            'username': ADMIN['ADMIN_LOCAL_USERNAME'], 'password': ADMIN['ADMIN_LOCAL_PASSWORD']})

    async def test_check_permission_audit_idempotency_and_diagnostic_access(self):
        path = ROOT + '/agent'
        body = {'operation_id': str(uuid4()), 'kind': 'provider', 'target_id': 'deepseek'}
        write = {'X-Admin-Request': '1'}
        self.assertEqual((await self.browser.post(path + '/checks', json=body, headers=write)).status_code, 401)
        await self.login()
        self.assertEqual((await self.browser.post(path + '/checks', json=body)).status_code, 403)
        self.assertEqual((await self.browser.post(path + '/checks', json=body,
                         headers={**write, 'Sec-Fetch-Site': 'cross-site'})).status_code, 403)
        checked = await self.browser.post(path + '/checks', json=body, headers=write)
        self.assertEqual(checked.status_code, 200, checked.text)
        self.assertEqual(checked.json()['data']['check']['state'], 'pass')
        self.assertEqual((await self.browser.post(path + '/checks', json=body, headers=write)).json(), checked.json())
        rejected = await self.browser.post(path + '/checks', json={**body, 'target_id': 'changed'}, headers=write)
        self.assertEqual(rejected.status_code, 409)
        online = {**body, 'operation_id': str(uuid4()), 'profile': 'network'}
        await self.browser.post(path + '/checks', json=online, headers=write)
        self.assertEqual((await self.browser.post(path + '/checks',
                         json={**online, 'operation_id': str(uuid4())}, headers=write)).status_code, 429)
        diagnosis = {'operation_id': str(uuid4()), 'kind': 'run', 'target_id': 'run0'}
        with patch.dict(os.environ, {'ADMIN_AGENT_DIAGNOSTICS': 'false'}):
            self.assertEqual((await self.browser.post(path + '/diagnostics', json=diagnosis, headers=write)).status_code, 403)
        result = await self.browser.post(path + '/diagnostics', json=diagnosis, headers=write)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()['data']['diagnostic'])
        diag = await self.browser.post(path + '/diagnostics/' + diagnosis['operation_id'] + '/view', headers=write)
        self.assertEqual(diag.status_code, 200, diag.text)
        self.assertEqual(diag.json()['data']['run_id'], 'run0')
        async with self.audit_db() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(EntitlementAuditRow)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(ManagementAuditRow)), 5)

    async def test_durable_budget_stops_online_probe_before_agent_call(self):
        await self.login()
        path = ROOT + '/agent'
        write = {'X-Admin-Request': '1'}
        with patch.object(audit, 'MAX_DAILY_TOKENS', audit.PROBE_RESERVATION):
            first = await self.browser.post(path + '/checks', headers=write, json={
                'operation_id': str(uuid4()), 'kind': 'model', 'target_id': MODEL, 'profile': 'completion',
            })
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()['data']['reason'], 'DEDICATED_PROBE_CREDENTIAL_REQUIRED')
            denied = await self.browser.post(path + '/checks', headers=write, json={
                'operation_id': str(uuid4()), 'kind': 'model', 'target_id': 'other/model', 'profile': 'completion',
            })
            self.assertEqual(denied.status_code, 429, denied.text)

    async def test_configuration_bridge_audit_and_blocked_replay(self):
        from fastapi.exceptions import RequestValidationError
        from app.core.responses import fail
        from app.models.agent_entitlements import GrantRevisionRow, GrantRootRow, UsageLedgerRow
        from app.services import agent_config_management
        from agent_contracts.management_config import ConfigSpec, Proof
        from agent_app.config_deployment import proof_signature
        from agent_app.infrastructure.models import RunRow, TaskRow
        from agent_app.management_workers import save
        from agent_contracts.management_phase2 import Capability
        from sqlalchemy import update

        @self.backend_app.exception_handler(RequestValidationError)
        async def safe_validation_error(_request, _error):
            return fail(10001, 'REQUEST_INVALID', 422)

        async with self.backend_engine.begin() as connection:
            for model in (GrantRootRow, GrantRevisionRow, UsageLedgerRow):
                await connection.run_sync(model.__table__.create)
        immutable_models = (
            bridge_module.EntitlementPolicyRow, bridge_module.PlanReleaseRow, bridge_module.OwnerEntitlementRow,
            GrantRootRow, GrantRevisionRow, UsageLedgerRow, EntitlementAuditRow, bridge_module.UsageProjectionRow,
        )
        async with self.audit_db.begin() as db:
            policy = await db.get(bridge_module.EntitlementPolicyRow, 'existing')
            policy.payload = {'permission_snapshot': {'capabilities': []}}

        async def protected_rows():
            async with self.audit_db() as db:
                return [(await db.execute(select(model.__table__))).all() for model in immutable_models]

        before = await protected_rows()
        path = ROOT + '/agent/config/revisions'
        write = {'X-Admin-Request': '1'}
        spec = ConfigSpec(build_revision='config-build', runtime_version='config-runtime',
                          providers=[{'provider_id': 'fixture', 'base_url': 'https://provider.example.invalid/v1',
                                      'secret_ref': 'AGENT_PROVIDER_SECRET_FIXTURE'}],
                          models=[{'model_id': 'fixture/m1', 'provider_id': 'fixture',
                                   'upstream_model_id': 'm1', 'label': 'Fixture'}])
        body = {'operation_id': str(uuid4()), 'base_revision': None, 'reason': 'isolated bridge',
                'spec': spec.model_dump(mode='json')}
        with patch.dict(os.environ, {'AGENT_CONFIG_MANAGEMENT_TOKEN': 'fixture-config-service-credential',
                                     'AGENT_CONFIG_VALIDATOR_SECRET': 'fixture-only-proof-key-not-for-deployment',
                                     'AGENT_CONFIG_WRITE_ENABLED': 'true', 'AGENT_CONFIG_SCHEDULING': 'enforce',
                                     'ADMIN_AGENT_CONFIG_WRITE_ENABLED': 'false'}), \
             patch.object(agent_config_management, 'get_session_factory', return_value=self.audit_db):
            self.assertEqual((await self.browser.post(path, json=body, headers=write)).status_code, 401)
            await self.login()
            self.assertEqual((await self.browser.post(path, json=body, headers=write)).status_code, 403)
            with patch.dict(os.environ, {'ADMIN_AGENT_CONFIG_WRITE_ENABLED': 'true'}):
                self.assertEqual((await self.browser.post(path, json=body)).status_code, 403)
                bad_spec = spec.model_dump(mode='json')
                bad_spec['providers'][0]['api_key'] = 'fixture-plaintext-must-not-leak'
                rejected = await self.browser.post(path, json={**body, 'spec': bad_spec}, headers=write)
                self.assertEqual(rejected.status_code, 422)
                self.assertNotIn('fixture-plaintext-must-not-leak', rejected.text)
                draft = await self.browser.post(path, json=body, headers=write)
                self.assertEqual(draft.status_code, 200, draft.text)
                self.assertEqual(draft.json()['data']['status'], 'draft')
                self.assertEqual((await self.browser.post(path, json=body, headers=write)).json(), draft.json())
                collision = await self.browser.post(path, json={**body, 'reason': 'changed'}, headers=write)
                self.assertEqual(collision.status_code, 409)
                proof = Proof(revision_id=body['operation_id'], config_digest=spec.config_digest,
                              build_revision='config-build', runtime_version='config-runtime',
                              observed_at=now_utc(), network_verified=False, signature='sha256:' + '0' * 64,
                              capabilities=[{'id': 'model:fixture/m1', 'version': digest('fixture')}])
                proof = proof.model_copy(update={'signature': proof_signature(proof)})
                validation = {'operation_id': str(uuid4()), 'reason': 'static only', 'expected_active_revision': None,
                              'proof': proof.model_dump(mode='json')}
                target = path + '/' + body['operation_id'] + '/validate'
                blocked = await self.browser.post(target, json=validation, headers=write)
                self.assertEqual(blocked.status_code, 200, blocked.text)
                self.assertIn('ISOLATED_NETWORK_PROOF_REQUIRED', blocked.json()['data']['blockers'])
                self.assertEqual((await self.browser.post(target, json=validation, headers=write)).json(), blocked.json())
                self.assertEqual((await self.browser.get(path)).status_code, 200)
                fleet = await self.browser.get(ROOT + '/agent/config/fleet/events?worker_id=worker-a')
                self.assertEqual(fleet.status_code, 200, fleet.text)
                self.assertIn('registered', [event['kind'] for event in fleet.json()['data']['items']])
                async with self.db.begin() as db:
                    await db.execute(update(TaskRow).values(status='succeeded'))
                    await db.execute(update(RunRow).values(status='succeeded'))

                async def promote(revision, candidate_spec, expected, action, worker_id, endpoint_version):
                    endpoint = f'{path}/{revision}'
                    candidate_proof = Proof(
                        revision_id=revision, config_digest=candidate_spec.config_digest,
                        build_revision=candidate_spec.build_revision, runtime_version=candidate_spec.runtime_version,
                        observed_at=now_utc(), network_verified=True, signature='sha256:' + '0' * 64,
                        capabilities=[{'id': 'model:fixture/m1', 'version': endpoint_version}],
                    )
                    candidate_proof = candidate_proof.model_copy(update={'signature': proof_signature(candidate_proof)})
                    validation_id, operation_id = str(uuid4()), str(uuid4())
                    valid = await self.browser.post(endpoint + '/validate', headers=write, json={
                        'operation_id': validation_id, 'reason': 'signed isolated test',
                        'expected_active_revision': expected, 'proof': candidate_proof.model_dump(mode='json'),
                    })
                    self.assertEqual(valid.json()['data']['status'], 'validated', valid.text)
                    staged = await self.browser.post(endpoint + '/' + action, headers=write, json={
                        'operation_id': operation_id, 'reason': 'isolated operation', 'approval_ref': 'fixture-approval',
                        'expected_active_revision': expected, 'validation_id': validation_id, 'worker_ids': [worker_id],
                    })
                    self.assertEqual(staged.status_code, 200, staged.text)
                    evidence = WorkerManifest(
                        config_revision=revision, config_digest=candidate_spec.config_digest,
                        build_revision=candidate_spec.build_revision, runtime_version=candidate_spec.runtime_version,
                        capabilities=[Capability(kind='model', id='fixture/m1', scope='loaded', version=endpoint_version)],
                    )
                    await save(worker_id, WorkerReport(
                        instance_id=uuid4(), sequence=1, started_at=now_utc(), lifecycle='running', health='ok',
                        manifest=evidence, manifest_digest=digest(evidence.model_dump(mode='json')),
                    ))
                    finished = await self.browser.post(
                        ROOT + '/agent/config/deployments/' + operation_id + '/reconcile',
                        headers=write, json={'operation_id': str(uuid4()), 'reason': 'confirmed fixture'},
                    )
                    self.assertEqual(finished.status_code, 200, finished.text)
                    return finished.json()['data']['status']

                old = body['operation_id']
                self.assertEqual(await promote(old, spec, None, 'activate', 'old', digest('old')), 'active')
                updated = spec.model_copy(update={'runtime_version': 'fixture-next'})
                new = str(uuid4())
                created = await self.browser.post(path, headers=write, json={
                    'operation_id': new, 'base_revision': old, 'reason': 'updated fixture',
                    'spec': updated.model_dump(mode='json'),
                })
                self.assertEqual(created.status_code, 200, created.text)
                self.assertEqual(await promote(new, updated, old, 'activate', 'new', digest('new')), 'active')
                self.assertEqual(await promote(old, spec, new, 'rollback', 'old-restaged', digest('old')), 'rolled_back')
                self.assertEqual(await protected_rows(), before)
        async with self.audit_db() as db:
            for model in (EntitlementAuditRow, GrantRootRow, GrantRevisionRow, UsageLedgerRow):
                self.assertEqual(await db.scalar(select(func.count()).select_from(model)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(ManagementAuditRow)), 12)

    async def test_tamper_detection(self):
        await self.login()
        path = ROOT + '/agent'
        body = {'operation_id': str(uuid4()), 'kind': 'provider', 'target_id': 'missing'}
        created = await self.browser.post(path + '/checks', json=body, headers={'X-Admin-Request': '1'})
        self.assertEqual(created.json()['data']['state'], 'fail')
        self.assertNotIn('"target_id":"missing"', created.text)
        self.assertEqual((await self.browser.get(path + '/audit?target_id=missing')).json()['data']['items'][0]['audit_id'],
                         body['operation_id'])
        async with self.audit_db.begin() as db:
            row = await db.get(ManagementAuditRow, body['operation_id'])
            row.reason = 'TAMPERED'
        self.assertEqual((await self.browser.get(path + '/audit/' + body['operation_id'])).status_code, 503)

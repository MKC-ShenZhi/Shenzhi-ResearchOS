"""Phase 4 regressions for real persisted evidence and audited operator actions."""
import base64
from datetime import timedelta
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from sqlalchemy import select
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from agent_contracts.canonical import canonical_json_v1, digest
from agent_contracts.management_operations import ActorManagementAction
from agent_contracts.management_config import ActorApproval
from agent_contracts.management_phase2 import WorkerReport
from agent_app import management_operations as ops, management_workers, config_approval
from agent_app.control.metering import now_utc, GateDenied
from agent_app.control import repository
from agent_app.infrastructure.models import RunRow
from agent_app.infrastructure.management_models import WorkerAlertRow, WorkerSnapshotRow, WorkerLifecycleRow
from tests import test_management_phase2 as phase2


class ManagementOperationsTests(phase2.ManagementAuditTests):
    async def test_candidate_preview_preserves_dependencies_and_rejects_invalid_defaults(self):
        from types import SimpleNamespace
        from pydantic import ValidationError
        from agent_contracts.management_config import Candidate, ConfigSpec
        from app.services import agent_config_management as config
        from app.models.agent_entitlements import GrantRootRow, GrantRevisionRow, EntitlementPolicyRow
        async with self.backend_engine.begin() as connection:
            await connection.run_sync(GrantRootRow.__table__.create)
            await connection.run_sync(GrantRevisionRow.__table__.create)
        spec = ConfigSpec(build_revision='fixture', runtime_version='0.1.0',
            providers=[dict(provider_id='fixture', base_url='https://provider.example.invalid/v1', secret_ref='AGENT_PROVIDER_SECRET_FIXTURE')],
            models=[dict(model_id=phase2.MODEL, provider_id='fixture', upstream_model_id='upstream', label='Fixture')],
            defaults={'chat': phase2.MODEL})
        async with self.audit_db.begin() as db:
            policy = await db.get(EntitlementPolicyRow, 'existing')
            policy.payload = {'permission_snapshot': {'capabilities': [{'capability_id': 'model:' + phase2.MODEL}]}}
        changed = spec.model_copy(update={'models': [spec.models[0].model_copy(update={'model_id': 'fixture/renamed'})],
                                         'defaults': {'chat': 'fixture/renamed'}})
        candidate = Candidate(operation_id=uuid4(), base_revision=uuid4(), reason='rename', spec=changed)
        with patch.object(config, 'get_session_factory', return_value=self.audit_db), \
                patch.object(config, 'read', AsyncMock(return_value=SimpleNamespace(spec=spec))):
            result = await config.preview(candidate)
        self.assertEqual(result['referencing_policies'], ['existing'])
        self.assertEqual(result['referencing_owners'], 1)
        self.assertTrue(result['client_references']['persisted_task_references'])
        self.assertEqual(result['client_references']['external_clients'], 'unknown')
        invalid = spec.model_dump(mode='json')
        invalid['models'][0]['enabled'] = False
        with self.assertRaises(ValidationError):
            ConfigSpec.model_validate(invalid)

    async def test_alert_timeout_recovery_dedup_and_close(self):
        async with self.db.begin() as db:
            worker = await db.get(WorkerSnapshotRow, 'worker-a')
            worker.observed_at = now_utc() - timedelta(minutes=3)
        await ops.inspect_heartbeats()
        await ops.inspect_heartbeats()
        async with self.db() as db:
            alerts = (await db.scalars(select(WorkerAlertRow))).all()
            self.assertEqual(len(alerts), 1)
            target = alerts[0].alert_id
        action = ActorManagementAction(operation_id=uuid4(), kind='alert', target_id=target,
                                       action='close', reason='review', actor='fixture')
        with self.assertRaises(GateDenied):
            await ops.act(action)
        await ops.act(action.model_copy(update={'operation_id': uuid4(), 'action': 'acknowledge'}))
        async with self.db() as db:
            worker = await db.get(WorkerSnapshotRow, 'worker-a')
            recovery = WorkerReport(instance_id=worker.instance_id, sequence=worker.sequence + 1,
                started_at=management_workers.utc(worker.started_at), lifecycle='running', health='ok')
        await management_workers.save('worker-a', recovery)
        await ops.inspect_heartbeats()
        await ops.inspect_heartbeats()
        result = await ops.act(action)
        self.assertEqual(await ops.act(action), result)
        with self.assertRaises(GateDenied):
            await ops.act(action.model_copy(update={'reason': 'different'}))
        async with self.db() as db:
            alert = await db.get(WorkerAlertRow, target)
            self.assertEqual(alert.state, 'closed')
            self.assertIsNotNone(alert.recovered_at)
            events = (await db.scalars(select(WorkerLifecycleRow).where(
                WorkerLifecycleRow.kind == 'heartbeat_timeout'))).all()
            self.assertEqual(len(events), 1)
            recovered = (await db.scalars(select(WorkerLifecycleRow).where(
                WorkerLifecycleRow.kind == 'heartbeat_recovered'))).all()
            self.assertEqual(len(recovered), 1)

    async def test_drain_blocks_claim_and_resume_is_audited(self):
        denied = await self.client.post('/internal/v2/management/config/actions',
            headers={'Authorization': 'Bearer ' + phase2.ENV['AGENT_MANAGEMENT_TOKEN']},
            json=dict(operation_id=str(uuid4()), kind='worker', target_id='worker-a', action='drain',
                      reason='denied', actor='forged'))
        self.assertEqual(denied.status_code, 403)
        await self.login()
        body = dict(operation_id=str(uuid4()), kind='worker', target_id='worker-a',
                    action='drain', reason='maintenance', timeout_seconds=10)
        path = phase2.ROOT + '/agent/actions'
        self.assertEqual((await self.browser.post(path, json=body)).status_code, 403)
        headers = {'X-Admin-Request': '1'}
        result = await self.browser.post(path, json=body, headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((await self.browser.post(path, json=body, headers=headers)).json(), result.json())
        async with self.db() as db:
            self.assertIsNone(await repository.claim_run(db, 'worker-a', v2=True))
        self.assertEqual((await ops.drain_state('worker-a'))['state'], 'draining')
        async with self.db.begin() as db:
            for run in (await db.scalars(select(RunRow))).all():
                run.lease_expires_at = now_utc() - timedelta(seconds=1)
                run.status = 'completed'
        self.assertEqual((await ops.drain_state('worker-a'))['state'], 'drained')
        resumed = await self.browser.post(path, json={**body, 'operation_id': str(uuid4()), 'action': 'resume'}, headers=headers)
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual((await ops.drain_state('worker-a'))['state'], 'accepting')
        entries = await phase2.audit.rows(0, 20, action='control')
        self.assertEqual(len(entries), 2)

    async def test_batch_summary_rejects_old_versions_and_expired_checks(self):
        await self.login()
        headers = {'X-Admin-Request': '1'}
        target = dict(kind='provider', target_id='deepseek')
        path = phase2.ROOT + '/agent'
        response = await self.browser.post(path + '/checks', json={**target, 'operation_id': str(uuid4())}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        async def summary():
            result = await self.browser.post(path + '/checks/summary', json={'targets': [target]}, headers=headers)
            self.assertEqual(result.status_code, 200, result.text)
            return result.json()['data']['items'][0]
        self.assertEqual((await summary())['state'], 'pass')
        with patch.dict(os.environ, {'DEEPSEEK_BASE_URL': 'https://changed.example.invalid/v1'}):
            self.assertEqual((await summary())['state'], 'stale')
        with patch.object(phase2.audit, 'now', return_value=now_utc() + timedelta(minutes=6)):
            self.assertEqual((await summary())['reason'], 'CHECK_EXPIRED')
        from agent_contracts.management_phase2 import StartProbe
        pending = StartProbe(operation_id=uuid4(), **target)
        await phase2.audit.admit('local-admin:test-admin', 'check', pending, str(uuid4()))
        self.assertEqual((await summary())['state'], 'pending')

    async def test_rejected_control_cannot_execute_on_replay_after_target_appears(self):
        await self.login()
        body = dict(operation_id=str(uuid4()), kind='worker', target_id='later-worker', action='drain', reason='review')
        url = phase2.ROOT + '/agent/actions'
        headers = {'X-Admin-Request': '1'}
        self.assertEqual((await self.browser.post(url, json=body, headers=headers)).status_code, 404)
        await management_workers.save('later-worker', WorkerReport(instance_id=uuid4(), sequence=1,
            started_at=now_utc(), lifecycle='running', health='ok'))
        self.assertEqual((await self.browser.post(url, json=body, headers=headers)).status_code, 409)
        self.assertEqual((await ops.drain_state('later-worker'))['state'], 'accepting')

    async def test_run_tool_evidence_requires_live_lease(self):
        from agent_app.management_observations import tool_runtime
        async with self.db() as db:
            worker = await db.get(WorkerSnapshotRow, 'worker-a')
            report = WorkerReport(instance_id=worker.instance_id, sequence=worker.sequence + 1,
                started_at=management_workers.utc(worker.started_at), lifecycle='running', health='ok',
                active_run_id='run0', run_tool_ids=['tool:web_search'], run_latent_tool_ids=['tool:fetch_url'])
        await management_workers.save('worker-a', report)
        self.assertEqual((await tool_runtime('tool:web_search', 'run0'))['run_callable'], 'yes')
        self.assertEqual((await tool_runtime('tool:fetch_url', 'run0'))['latent'], 'yes')
        async with self.db.begin() as db:
            run = await db.get(RunRow, 'run0')
            run.lease_expires_at = now_utc() - timedelta(seconds=1)
        self.assertEqual((await tool_runtime('tool:web_search', 'run0'))['run_callable'], 'unknown')

    async def test_cancel_uses_trusted_owner_and_replays_receipt(self):
        await self.login()
        from app.services.agent_management_operations import AgentGatewayV2
        body = dict(operation_id=str(uuid4()), kind='task', target_id='task0', action='cancel', reason='stop')
        with patch.object(AgentGatewayV2, 'cancel', AsyncMock(return_value={'status': 'cancelling'})) as cancel:
            result = await self.browser.post(phase2.ROOT + '/agent/actions', json=body, headers={'X-Admin-Request': '1'})
            self.assertEqual(result.status_code, 200, result.text)
            cancel.assert_awaited_once_with('task0', 'user:alice')
            replay = await self.browser.post(phase2.ROOT + '/agent/actions', json=body, headers={'X-Admin-Request': '1'})
            self.assertEqual(replay.json(), result.json())
            self.assertEqual(cancel.await_count, 1)

    async def test_external_approval_signature_binding(self):
        import json
        key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        revision, validation = str(uuid4()), uuid4()
        proof = dict(approver='reviewer', revision_id=revision, validation_id=str(validation),
                     validation_digest=digest('reviewed'), observed_at=now_utc().isoformat())
        proof['signature'] = base64.b64encode(key.sign(canonical_json_v1(proof))).decode()
        body = ActorApproval(operation_id=uuid4(), validation_id=validation, expected_active_revision=None,
            reason='approved', actor='ssh-admin:operator', external_proof=proof)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'reviewer.pem'
            path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
            with patch.dict(os.environ, {'AGENT_CONFIG_APPROVER_PUBLIC_KEYS': json.dumps({'reviewer': str(path)})}):
                self.assertEqual(config_approval.approver(body, revision, digest('reviewed')), 'external-approver:reviewer')
                with self.assertRaises(GateDenied):
                    config_approval.approver(body, revision, digest('different'))

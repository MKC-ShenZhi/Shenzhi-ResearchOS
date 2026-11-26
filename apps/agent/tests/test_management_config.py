"""Fault injection for the immutable release coordinator and the real lease repository."""
import asyncio
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_contracts import TaskSubmission
from agent_contracts.canonical import digest
from agent_contracts.management_config import (
    ActorAdmissionChange, ActorApproval, ActorCandidate, ActorReconcile, ActorSwitch, ActorValidate, CapabilityVersion,
    ConfigSpec, Impact, PreparedRelease, Proof,
)
from agent_contracts.management_phase2 import Capability, WorkerManifest, WorkerReport
from agent_app import config_deployment as deploy, config_scheduling
from agent_app import management_observations, management_workers
from agent_app.control import repository
from agent_app.errors import BusinessError
from agent_app.execution.config_profile import load_profile, registry_for
from agent_app.worker.management_reporter import manifest
from agent_app.control.metering import GateDenied, now_utc
from agent_app.infrastructure.config_management_models import ConfigOperationRow, TaskExecutionConstraintRow
from agent_app.infrastructure.metering_models import ExecutionRow, TaskMeteringRow
from agent_app.infrastructure.models import Base, RunRow, TaskRow

MODEL = 'fixture/m1'
VERSION = digest('model-identity')
EMPTY = Impact(affected_grants=0, impacted_owners=0)
ACTOR = 'local-admin:fixture'


class ConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_secret_reference_rotation_keeps_old_registry_and_rejects_missing_injection(self):
        original = self.candidate().spec
        rotated = original.model_copy(update={'providers': [original.providers[0].model_copy(
            update={'secret_ref': 'AGENT_PROVIDER_SECRET_ROTATED'})]})
        env = {'AGENT_CONFIG_PROVIDER_ORIGINS': 'https://provider.example.invalid',
               'AGENT_CONFIG_SECRET_REFS': 'AGENT_PROVIDER_SECRET_FIXTURE AGENT_PROVIDER_SECRET_ROTATED',
               'AGENT_PROVIDER_SECRET_FIXTURE': 'isolated-old-running-key',
               'AGENT_PROVIDER_SECRET_ROTATED': 'isolated-new-running-key'}
        with patch.dict(os.environ, env):
            old = registry_for(original)
            new = registry_for(rotated)
            self.assertNotEqual(old.resolve_model(MODEL).key, new.resolve_model(MODEL).key)
            self.assertNotIn('isolated-new-running-key', json.dumps(new.public_models('agent')))
            with patch.dict(os.environ, {'AGENT_PROVIDER_SECRET_ROTATED': ''}):
                with self.assertRaises(BusinessError):
                    registry_for(rotated)
            self.assertEqual(old.resolve_model(MODEL).key, 'isolated-old-running-key')

    async def asyncSetUp(self):
        server = os.getenv('SHENZHI_PHASE3_AGENT_TEST_DSN', '')
        if server and ('@127.0.0.1:' not in server or '/phase3accept?' not in server):
            raise RuntimeError('Phase 3 integration requires its disposable loopback database')
        schema = 'phase3_' + uuid4().hex
        engine_kwargs = {'connect_args': {'server_settings': {'search_path': schema}}} if server else {}
        self.engine = create_async_engine(server or 'sqlite+aiosqlite:///:memory:', hide_parameters=True, **engine_kwargs)
        self.addAsyncCleanup(self.engine.dispose)
        if server:
            async with self.engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA {schema}'))
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)
        self.instances = {}

        async def access():
            async with self.db() as db:
                yield db

        observer = patch.object(management_observations, 'get_session', access)
        observer.start()
        self.addCleanup(observer.stop)
        flags = patch.dict(os.environ, {'AGENT_CONFIG_WRITE_ENABLED': 'true', 'AGENT_CONFIG_SCHEDULING': 'enforce',
                                        'AGENT_CONFIG_VALIDATOR_SECRET': 'fixture-only-proof-key-not-for-deployment'})
        flags.start()
        self.addCleanup(flags.stop)

    def candidate(self, label='First', base=None):
        return ActorCandidate(operation_id=uuid4(), actor=ACTOR, reason='fixture', base_revision=base, spec=ConfigSpec(
            build_revision='build-test', runtime_version='runtime-test',
            providers=[{'provider_id': 'fixture', 'base_url': 'https://provider.example.invalid/v1',
                        'secret_ref': 'AGENT_PROVIDER_SECRET_FIXTURE'}],
            models=[{'model_id': MODEL, 'provider_id': 'fixture', 'upstream_model_id': 'm1', 'label': label,
                     'capabilities': {'tool_calling': True}}]))

    def proof(self, candidate, network=True):
        proof = Proof(revision_id=candidate.operation_id, config_digest=candidate.spec.config_digest,
                      build_revision='build-test', runtime_version='runtime-test', observed_at=now_utc(),
                      capabilities=[CapabilityVersion(id='model:' + MODEL, version=VERSION)],
                      network_verified=network, signature='sha256:' + '0' * 64)
        return proof.model_copy(update={'signature': deploy.proof_signature(proof)})

    async def validate(self, candidate, active=None, network=True, impact=EMPTY):
        body = ActorValidate(operation_id=uuid4(), actor=ACTOR, reason='validation fixture',
                             expected_active_revision=active, proof=self.proof(candidate, network), impact=impact)
        return await deploy.mutate('validate', body, str(candidate.operation_id))

    async def worker(self, worker_id, candidate, version=VERSION, *, stale=False):
        manifest = WorkerManifest(
            config_revision=str(candidate.operation_id), config_digest=candidate.spec.config_digest,
            build_revision='build-test', runtime_version='runtime-test',
            capabilities=[Capability(kind='model', id=MODEL, scope='loaded', version=version)])
        instance = uuid4()
        await management_workers.save(worker_id, WorkerReport(
            instance_id=instance, sequence=1, started_at=now_utc() - timedelta(seconds=1),
            lifecycle='running', health='ok', manifest_digest=digest(manifest.model_dump(mode='json')), manifest=manifest))
        if stale:
            from agent_app.infrastructure.management_models import WorkerSnapshotRow
            async with self.db.begin() as db:
                row = await db.get(WorkerSnapshotRow, worker_id)
                row.observed_at = now_utc() - timedelta(minutes=3)
        self.instances[worker_id] = str(instance)
        return manifest

    async def switch(self, candidate, validation, workers, before=None, action='activate'):
        request = ActorSwitch(operation_id=uuid4(), actor=ACTOR, reason='rollout fixture', approval_ref='fixture-approval',
                              expected_active_revision=before, validation_id=validation.operation_id,
                              worker_ids=workers, impact=EMPTY)
        return request, await deploy.mutate(action, request, str(candidate.operation_id))

    async def reconcile(self, operation):
        operation_id = uuid4()
        evidence = PreparedRelease(deployment_id=operation.operation_id, operation_id=operation_id,
                                   fencing_token=operation.fencing_token, target_revision=operation.revision_id,
                                   validation_digest=operation.validation_digest, impact_digest=digest(EMPTY.model_dump(mode='json')),
                                   prepared_at=now_utc())
        return await deploy.mutate('reconcile', ActorReconcile(operation_id=operation_id, actor=ACTOR,
                                   reason='verify fixture', impact=EMPTY, fencing_token=operation.fencing_token,
                                   preparation=evidence), str(operation.operation_id))

    async def task(self):
        submission = TaskSubmission(owner_id='user:fixture', prompt='fixture', model=MODEL, idempotency_key=uuid4().hex)
        metering = SimpleNamespace(submission_id=uuid4().hex, metering_profile_id=uuid4().hex,
                                  metering_context='authorized', model_dump=lambda **kwargs: {},
                                  budget_grant=SimpleNamespace(capabilities=[
                                      SimpleNamespace(capability_id='model:' + MODEL, capability_version=VERSION)]))
        async with self.db() as db:
            record = await repository.submit(db, submission, metering=metering)
            row = await db.get(TaskMeteringRow, record.task_id)
            row.binding_status = 'bound'
            await db.commit()
        return record

    async def claim(self, worker_id, evidence):
        async with self.db() as db:
            with patch('agent_app.config_scheduling.worker_evidence', return_value=evidence):
                return await repository.claim_run(db, worker_id, v2=True)

    async def test_immutable_revisions_replay_approval_and_cas(self):
        draft = self.candidate()
        a = await deploy.mutate('create', draft)
        self.assertEqual(a, await deploy.mutate('create', draft))
        with self.assertRaisesRegex(GateDenied, 'CONFIG_OPERATION_CONFLICT'):
            await deploy.mutate('create', draft.model_copy(update={'reason': 'different'}))
        edited = self.candidate(label='Updated', base=draft.operation_id)
        await deploy.mutate('create', edited)
        self.assertNotEqual(draft.spec.config_digest, edited.spec.config_digest)
        self.assertEqual((await deploy.view(str(draft.operation_id))).spec.models[0].label, 'First')
        self.assertEqual((await self.validate(draft, network=False)).status, 'blocked')
        self.assertEqual((await self.validate(draft, impact=Impact(affected_grants=1, impacted_owners=1))).status, 'blocked')
        validated = await self.validate(draft)
        await self.worker('a', draft)
        request, rollout = await self.switch(draft, validated, ['a'])
        self.assertEqual(rollout.status, 'deploying')
        self.assertIsNone((await deploy.view()).active_revision)
        self.assertEqual((await self.reconcile(rollout)).status, 'active')
        self.assertEqual(await deploy.mutate('activate', request, str(draft.operation_id)), rollout)
        with self.assertRaisesRegex(GateDenied, 'CONFIG_CAS_CONFLICT'):
            await self.validate(edited)

    async def test_fence_preparation_and_distinct_approval(self):
        draft = self.candidate()
        await deploy.mutate('create', draft)
        validated = await self.validate(draft)
        approval = ActorApproval(operation_id=uuid4(), actor=ACTOR, reason='fixture approval',
                                 validation_id=validated.operation_id, expected_active_revision=None)
        await self.worker('a', draft)
        with patch.dict(os.environ, {'AGENT_CONFIG_REQUIRE_SEPARATE_APPROVAL': 'true'}):
            with self.assertRaisesRegex(GateDenied, 'CONFIG_APPROVER_MUST_BE_DISTINCT'):
                await deploy.mutate('approve', approval, str(draft.operation_id))
            self.assertEqual((await deploy.mutate('approve', approval.model_copy(update={'actor': 'local-admin:reviewer'}),
                                                str(draft.operation_id))).status, 'approved')
            switched = await deploy.mutate('activate', ActorSwitch(
                operation_id=uuid4(), actor=ACTOR, reason='fixture rollout', approval_ref=str(approval.operation_id),
                expected_active_revision=None, validation_id=validated.operation_id, worker_ids=['a'], impact=EMPTY,
            ), str(draft.operation_id))
        self.assertEqual((await deploy.view()).pause_operation_id, switched.operation_id)
        with self.assertRaisesRegex(GateDenied, 'CONFIG_DEPLOYMENT_OWNS_ADMISSION'):
            await deploy.mutate('admission', ActorAdmissionChange(
                operation_id=uuid4(), actor=ACTOR, reason='stale resume', paused=False, expected_active_revision=None,
                expected_pause_operation_id=switched.operation_id))
        body = ActorReconcile(operation_id=uuid4(), actor=ACTOR, reason='stale fence', impact=EMPTY,
                              fencing_token=switched.fencing_token + 1)
        with self.assertRaisesRegex(GateDenied, 'CONFIG_DEPLOYMENT_FENCE_CONFLICT'):
            await deploy.mutate('reconcile', body, str(switched.operation_id))
        with self.assertRaisesRegex(GateDenied, 'CONFIG_PREPARATION_REQUIRED'):
            await deploy.mutate('reconcile', body.model_copy(update={'fencing_token': switched.fencing_token}),
                                str(switched.operation_id))
        self.assertEqual((await self.reconcile(switched)).status, 'active')
        self.assertFalse((await deploy.view()).admission_paused)

    async def test_artifact_history_rejects_mutation_and_returns_only_document_preview(self):
        from agent_app.config_artifact_history import skill_snapshot, tool_snapshot
        from agent_app.execution.metering import controlled_resource_digest
        from agent_contracts.management_config import Artifact

        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            unpacked = root / 'temporary'
            (unpacked / 'scripts').mkdir(parents=True)
            (unpacked / 'SKILL.md').write_text('# example <script>unsafe</script>', encoding='utf-8')
            (unpacked / 'scripts' / 'example.py').write_text('print("fixture")', encoding='utf-8')
            identity = controlled_resource_digest(unpacked)
            version_root = root / identity.removeprefix('sha256:')
            version_root.mkdir()
            skill = unpacked.rename(version_root / 'example')
            item = Artifact(id='skill:example', digest=identity)
            with patch.dict(os.environ, {'AGENT_CONFIG_SKILL_ARTIFACT_ROOT': str(root),
                                        'AGENT_CONFIG_TOOL_METADATA_ROOT': str(root)}):
                self.assertIn('<script>', skill_snapshot(item, digest('SKILL.md'))['preview'])
                with self.assertRaisesRegex(GateDenied, 'RESOURCE_NOT_AVAILABLE'):
                    skill_snapshot(item, digest('scripts/example.py'))
                (skill / 'SKILL.md').write_text('altered', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                    skill_snapshot(item, None)
                metadata = {'description': 'fixture', 'parameters_schema': {'type': 'object'}, 'dependency_digests': []}
                identity = digest(metadata)
                (root / (identity.removeprefix('sha256:') + '.json')).write_text(json.dumps(metadata), encoding='utf-8')
                self.assertEqual(tool_snapshot(Artifact(id='tool:fixture', digest=VERSION,
                                                       metadata_digest=identity))['state'], 'available')
                self.assertEqual(tool_snapshot(Artifact(id='tool:fixture', digest=VERSION))['state'], 'unavailable')

    async def test_repeatable_versions_claim_takeover_and_parallel_rollback(self):
        old = self.candidate()
        await deploy.mutate('create', old)
        old_validation = await self.validate(old)
        old_worker = await self.worker('old', old)
        _, prior = await self.switch(old, old_validation, ['old'])
        self.assertEqual((await self.reconcile(prior)).status, 'active')
        first = await self.task()
        new = self.candidate('new', old.operation_id)
        await deploy.mutate('create', new)
        new_validation = await self.validate(new, old.operation_id)
        next_worker = await self.worker('new', new)
        _, deploy_new = await self.switch(new, new_validation, ['new', 'new-b'], old.operation_id)
        self.assertEqual((await self.reconcile(deploy_new)).status, 'partially_deployed')
        async with self.db.begin() as db:
            item = await db.get(ConfigOperationRow, str(deploy_new.operation_id))
            item.details = {**item.details, 'deadline': '2000-01-01T00:00:00+00:00'}
        self.assertEqual((await self.reconcile(deploy_new)).status, 'pending_reconcile')
        await self.worker('new-b', new)
        self.assertEqual((await self.reconcile(deploy_new)).status, 'active')
        second = await self.task()
        self.assertIsNone(await self.claim('absent', None))
        wrong = next_worker.model_copy(update={'build_revision': 'wrong-build'})
        self.assertIsNone(await self.claim('wrong', wrong))
        claimed = await self.claim('new', next_worker)
        self.assertEqual(claimed[0].task_id, second.task_id)
        old_claimed = await self.claim('old', old_worker)
        self.assertEqual(old_claimed[0].task_id, first.task_id)
        async with self.db.begin() as db:
            run = await db.get(RunRow, old_claimed[0].run_id)
            run.lease_expires_at = now_utc() - timedelta(seconds=1)
        self.assertIsNone(await self.claim('new', next_worker))
        takeover = await self.claim('old', old_worker)
        self.assertEqual(takeover[1], old_claimed[1] + 1)
        async with self.db() as db:
            history = (await db.scalars(select(ExecutionRow).where(
                ExecutionRow.task_id == first.task_id).order_by(ExecutionRow.lease_token))).all()
            self.assertEqual([item.sealed for item in history], [True, False])
        stale_proof = self.proof(old).model_copy(update={'observed_at': now_utc() - timedelta(hours=2)})
        stale_proof = stale_proof.model_copy(update={'signature': deploy.proof_signature(stale_proof)})
        with self.assertRaisesRegex(GateDenied, 'CONFIG_PROOF_STALE'):
            await deploy.mutate('validate', ActorValidate(operation_id=uuid4(), actor=ACTOR, reason='expired rollback',
                                expected_active_revision=new.operation_id, proof=stale_proof, impact=EMPTY),
                                str(old.operation_id))
        fresh = await self.validate(old, new.operation_id)
        _, rollback = await self.switch(old, fresh, ['old', 'old-offline'], new.operation_id, action='rollback')
        partial = await self.reconcile(rollback)
        self.assertEqual(partial.status, 'partially_deployed')
        self.assertEqual((await deploy.view()).active_revision, new.operation_id)
        await self.worker('old-offline', old)
        self.assertEqual((await self.reconcile(rollback)).status, 'rolled_back')
        async with self.db() as db:
            bound = await db.get(TaskExecutionConstraintRow, second.task_id)
            self.assertEqual(bound.revision_id, str(new.operation_id))
            row = await db.get(TaskRow, second.task_id)
            self.assertEqual(row.request_json['model'], MODEL)

    async def test_candidate_artifact_validates_normalization_build_and_secret(self):
        candidate = self.candidate()
        spec = candidate.spec.model_dump(mode='json')
        second_model = {**spec['models'][0], 'model_id': 'fixture/m2', 'upstream_model_id': 'm2'}
        spec['models'].append(second_model)
        normalized = ConfigSpec.model_validate(spec)
        self.assertEqual(normalized.config_digest,
                         ConfigSpec.model_validate({**spec, 'models': spec['models'][::-1]}).config_digest)
        with self.assertRaises(ValidationError):
            ConfigSpec.model_validate({**spec, 'defaults': {'agent': 'missing'}})
        self.addCleanup(load_profile.cache_clear)
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'candidate.json'
            path.write_text(json.dumps({'revision_id': str(candidate.operation_id), 'config_digest': normalized.config_digest,
                                        'spec': normalized.normalized()}), encoding='utf-8')
            with patch.dict(os.environ, {'AGENT_EXECUTION_CONFIG_FILE': str(path), 'AGENT_BUILD_REVISION': 'wrong-build'}):
                load_profile.cache_clear()
                with self.assertRaises(BusinessError):
                    load_profile()
            with patch.dict(os.environ, {'AGENT_EXECUTION_CONFIG_FILE': str(path), 'AGENT_BUILD_REVISION': 'build-test',
                                        'AGENT_CONFIG_WORKER_ROLE': 'candidate',
                                        'AGENT_CONFIG_PROVIDER_ORIGINS': 'https://provider.example.invalid',
                                        'AGENT_CONFIG_SECRET_REFS': 'AGENT_PROVIDER_SECRET_FIXTURE',
                                        'AGENT_PROVIDER_SECRET_FIXTURE': ''}):
                load_profile.cache_clear()
                revision, loaded = load_profile()
                self.assertEqual(revision, str(candidate.operation_id))
                with self.assertRaises(BusinessError):
                    registry_for(loaded)
                with patch.dict(os.environ, {'AGENT_PROVIDER_SECRET_FIXTURE': 'fixture-key-not-returned'}), \
                     patch('agent_app.worker.management_reporter.runtime_version', return_value='runtime-test'):
                    evidence = manifest()
                    self.assertEqual(evidence.config_digest, normalized.config_digest)
                    self.assertNotIn('fixture-key-not-returned', evidence.model_dump_json())
                with self.assertRaisesRegex(GateDenied, 'CANDIDATE_EXECUTION_DISABLED'):
                    await self.task()
                async with self.db() as db:
                    self.assertIsNone(await repository.claim_run(db, 'candidate', v2=True))

    async def test_authenticated_worker_evidence_and_concurrent_claim(self):
        draft = self.candidate()
        await deploy.mutate('create', draft)
        validated = await self.validate(draft)
        await self.worker('a', draft)
        await self.worker('b', draft)
        await self.worker('stale', draft, stale=True)
        _, staged = await self.switch(draft, validated, ['a', 'b'])
        self.assertEqual((await self.reconcile(staged)).status, 'active')
        task = await self.task()
        tokens = {name: uuid4().hex for name in self.instances}
        keyring = {name: hashlib.sha256(token.encode()).hexdigest() for name, token in tokens.items()}
        with patch.dict(os.environ, {'AGENT_WORKER_REPORT_IDENTITIES': json.dumps(keyring)}):
            async with self.db() as db:
                self.assertIsNone(await config_scheduling.worker_evidence(db, 'a', self.instances['a'], tokens['b']))
                self.assertIsNone(await config_scheduling.worker_evidence(db, 'a', self.instances['b'], tokens['a']))
                self.assertIsNone(await config_scheduling.worker_evidence(db, 'stale', self.instances['stale'], tokens['stale']))

            async def claim(name):
                async with self.db() as db:
                    return await repository.claim_run(db, name, v2=True, worker_instance=self.instances[name],
                                                      worker_report_token=tokens[name])

            if self.engine.dialect.name == 'postgresql':
                results = await asyncio.gather(claim('a'), claim('b'))
            else:
                results = [await claim('a'), await claim('b')]
            claimed = [item for item in results if item]
            self.assertEqual(len(claimed), 1)
            self.assertEqual(claimed[0][0].task_id, task.task_id)

    async def test_legacy_shadow_and_pause(self):
        with patch.dict(os.environ, {'AGENT_CONFIG_SCHEDULING': 'shadow'}):
            task = await self.task()
            with self.assertLogs('agent_app.config_scheduling', level='INFO') as messages:
                result = await self.claim('legacy-worker', None)
            self.assertEqual(result[0].task_id, task.task_id)
            self.assertIn('compatible=False', messages.output[0])
            operation = await deploy.mutate('admission', ActorAdmissionChange(
                operation_id=uuid4(), actor=ACTOR, reason='fixture drain', paused=True, expected_active_revision=None))
            self.assertEqual(operation.status, 'admission_paused')
            async with self.db() as db:
                with self.assertRaisesRegex(GateDenied, 'CONFIG_ADMISSION_PAUSED'):
                    await repository.submit(db, TaskSubmission(owner_id='user:test', prompt='paused'))
        draft = self.candidate()
        await deploy.mutate('create', draft)
        self.assertIn('LEGACY_TASKS_REQUIRE_DRAIN', (await self.validate(draft)).blockers)

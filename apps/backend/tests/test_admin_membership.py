"""Admin gift contract and opt-in PostgreSQL tests, isolated in random schemas."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from agent_contracts.canonical import digest
from agent_contracts.v2 import ModelIdentity, SkillIdentity
from app.models.agent_entitlements import OwnerEntitlementRow, EntitlementAuditRow
from app.schemas.admin import AdminUsersResponse
from app.schemas.admin_plans import AssignPlans, PublishPlans
from app.services.admin_users import list_users
from app.services.agent_entitlements import admin
from app.services.agent_entitlements.dates import add_calendar_months
from app.services.agent_entitlements.plans import build
from app.services.agent_entitlements.service import EntitlementError, Entitlements


def request(plan='basic', **kwargs):
    return AssignPlans(operation_id=uuid.uuid4().hex, reason='membership test',
        user_ids=['test'], plan_id=plan, policy_revision=f'{plan}-v1-test', **kwargs)


class AdminMembershipContractTests(unittest.TestCase):
    def test_duration_required_and_strict(self):
        for plan in ('pro', 'research'):
            for invalid in (None, 0, 13, True, '1', 1.0, -1):
                with self.subTest(plan=plan, invalid=invalid), self.assertRaises(ValidationError):
                    request(plan, duration_months=invalid)
            for months in (1, 12):
                self.assertEqual(request(plan, duration_months=months).duration_months, months)
        self.assertIsNone(request().duration_months)
        for months in (0, 1):
            with self.assertRaises(ValidationError):
                request(duration_months=months)
        with self.assertRaises(ValidationError):
            request(action='restore', duration_months=1)


URL = os.getenv('ADMIN_MEMBERSHIP_TEST_DATABASE_URL', '')


@unittest.skipUnless(URL, 'ADMIN_MEMBERSHIP_TEST_DATABASE_URL not selected')
class AdminMembershipPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        parsed = urlsplit(URL)
        if parsed.hostname not in ('127.0.0.1', 'localhost') or not parsed.path.endswith('_test'):
            raise RuntimeError('Requires an explicitly selected local *_test database')
        self.schema = 'admin_membership_' + uuid.uuid4().hex
        self.engine = create_async_engine(URL, connect_args={'server_settings': {'search_path': self.schema}})
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await connection.run_sync(self.migrate)
            await connection.execute(text('CREATE TABLE "user" (id TEXT PRIMARY KEY, email TEXT, name TEXT, "createdAt" TIMESTAMPTZ)'))
            await connection.execute(text('INSERT INTO "user" VALUES (:id, :email, :name, :created)'),
                {'id': 'test', 'email': 'test@example.test', 'name': 'Test',
                 'created': datetime(2026, 1, 1, tzinfo=timezone.utc)})
        model = ModelIdentity(schema_version=1, kind='model', capability_id='model:test/m1',
            provider_id='test', registry_model_id='test/m1', upstream_model='m1',
            configuration_release_digest=digest('test-config'), dependency_digests=[])
        skill = SkillIdentity(schema_version=1, kind='skill', capability_id='skill:deep-research',
            resource_content_digest=digest('test-skill'), dependency_digests=[])
        catalog = {'capabilities': [{'identity': i.model_dump(mode='json'),
            'version': digest(i.model_dump(mode='json'))} for i in (model, skill)]}
        bundle = build(catalog, release='test', model_budgets={'model:test/m1': dict(schema_version=1,
            input_basis='risk_assessed_utf8_v1', input_overhead_tokens=5, context_window_tokens=100,
            max_output_tokens=15, output_limit_semantics='completion_including_reasoning')}, risk_profile='test-risk')
        async with self.scope() as db:
            await admin.publish(db, PublishPlans(**bundle, operation_id='publish-test', reason='test',
                approval_ref='review', risk_approval_ref='risk'), 'local-admin:test',
                {'models': [{'value': 'test/m1', 'enabled': True}], 'skills': [{'name': 'deep-research'}]})

    @staticmethod
    def migrate(connection):
        for name in ('027_agent_entitlements', '028_formal_plans', '029_billing'):
            path = Path(__file__).resolve().parents[1] / 'migrations/versions' / (name + '.py')
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()

    @asynccontextmanager
    async def scope(self):
        async with self.factory() as db, db.begin():
            yield db

    async def asyncTearDown(self):
        async with self.engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await self.engine.dispose()

    async def apply(self, body):
        async with self.scope() as db:
            return await admin.assign(db, body, 'local-admin:test')

    async def test_preview_overwrite_calendar_and_replay(self):
        await self.apply(request('research', duration_months=12, preview=False))
        fixed = datetime(2028, 1, 31, 12, tzinfo=timezone.utc)
        body = request('pro', duration_months=1)
        async with self.scope() as db:
            owner = await db.get(OwnerEntitlementRow, 'user:test')
            owner.expires_at = fixed + timedelta(days=400)
        with patch.object(admin, 'now_utc', return_value=fixed):
            preview = await self.apply(body)
            item = preview['items'][0]
            self.assertEqual(item['status'], 'preview')
            self.assertEqual(item['after']['expires_at'], add_calendar_months(fixed, 1).isoformat())
            self.assertGreater(datetime.fromisoformat(item['before']['expires_at']),
                               datetime.fromisoformat(item['after']['expires_at']))
            self.assertTrue(item['after']['enabled'])
            self.assertEqual(item['after']['source'], 'admin')
            async with self.scope() as db:
                owner = await db.get(OwnerEntitlementRow, 'user:test')
                self.assertEqual(owner.plan_id, 'research')
                self.assertEqual(owner.expires_at, fixed + timedelta(days=400))
            body = body.model_copy(update={'preview': False})
            executed = await self.apply(body)
        self.assertEqual(await self.apply(body), executed)
        async with self.scope() as db:
            audit = await db.scalar(select(EntitlementAuditRow).where(EntitlementAuditRow.operation_id == body.operation_id))
            self.assertEqual(audit.payload['result'], executed)
            self.assertEqual(audit.payload['request']['duration_months'], 1)
        with self.assertRaises(EntitlementError) as exc:
            await self.apply(body.model_copy(update={'duration_months': 2}))
        self.assertEqual(exc.exception.reason, 'IDEMPOTENCY_CONFLICT')

    async def test_basic_is_permanent_and_disabled_requires_restore(self):
        await self.apply(request('pro', duration_months=1, preview=False))
        result = await self.apply(request(preview=False))
        self.assertIsNone(result['items'][0]['after']['expires_at'])
        await self.apply(request(action='disable', preview=False))
        result = await self.apply(request('research', duration_months=1, preview=False))
        self.assertEqual(result['items'][0]['reason'], 'ENTITLEMENT_DISABLED')
        restored = await self.apply(request(action='restore', preview=False))
        self.assertTrue(restored['items'][0]['after']['enabled'])
        self.assertIsNone(restored['items'][0]['after']['expires_at'])

    async def test_initialize_only_and_partial_success(self):
        body = request(initialize_only=True, preview=False).model_copy(update={'user_ids': ['test', 'missing']})
        result = await self.apply(body)
        self.assertEqual({i['user_id']: i['status'] for i in result['items']}, {'test': 'success', 'missing': 'failed'})
        result = await self.apply(request(initialize_only=True, preview=False))
        self.assertEqual(result['items'][0]['reason'], 'EXISTING_ASSIGNMENT_PRESERVED')
        result = await self.apply(request('pro', duration_months=1, initialize_only=True, preview=False))
        self.assertEqual(result['items'][0]['reason'], 'EXISTING_ASSIGNMENT_PRESERVED')

    async def test_list_expiry_and_legacy_permanent_are_honest_read_only(self):
        await self.apply(request('pro', duration_months=1, preview=False))
        async with self.scope() as db:
            owner = await db.get(OwnerEntitlementRow, 'user:test')
            owner.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        async with self.scope() as db:
            data = await list_users(db, page=1, page_size=20, search='', plan_id=None)
            item = AdminUsersResponse.model_validate(data).items[0]
            self.assertEqual(item.entitlement_status, 'expired')
            self.assertFalse(item.model_calls_enabled)
            self.assertEqual(item.source, 'admin')
            owner = await db.get(OwnerEntitlementRow, 'user:test')
            self.assertEqual(owner.plan_id, 'pro')
            owner.expires_at = None
        async with self.scope() as db:
            item = (await list_users(db, page=1, page_size=20, search='', plan_id=None))['items'][0]
            self.assertEqual(item['entitlement_status'], 'ready')
            self.assertTrue(item['model_calls_enabled'])
            self.assertIsNone(item['expires_at'])

    async def test_active_grants_block_switch_and_project_pending_expiry(self):
        await self.apply(request('pro', duration_months=1, preview=False))
        entitlements = Entitlements(issuer='test', audience='test', kid='test',
            private_key=Ed25519PrivateKey.generate())
        async with self.scope() as db:
            await entitlements.authorize_submission(db, owner_id='user:test', client_key=uuid.uuid4().hex,
                request={'owner_id': 'user:test', 'prompt': 'test', 'model': 'test/m1', 'skills': []})
        result = await self.apply(request('research', duration_months=1, preview=False))
        self.assertEqual(result['items'][0]['reason'], 'ACTIVE_GRANTS_REQUIRE_DRAIN')
        async with self.scope() as db:
            owner = await db.get(OwnerEntitlementRow, 'user:test')
            self.assertEqual(owner.plan_id, 'pro')
            owner.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        async with self.scope() as db:
            item = (await list_users(db, page=1, page_size=20, search='', plan_id=None))['items'][0]
            self.assertEqual(item['entitlement_status'], 'expiry_pending')
            self.assertFalse(item['model_calls_enabled'])

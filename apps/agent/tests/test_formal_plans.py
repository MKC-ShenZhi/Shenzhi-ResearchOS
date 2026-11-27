"""Formal plans exercise real Backend and Agent databases and signed permits.

Synthetic identities/risk approvals are test fixtures only; no real Provider.
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import select, text
from agent_contracts.canonical import digest
from agent_contracts.v2 import SkillIdentity
from agent_contracts.execution_v2 import CallIntent
from agent_app.control.metering import GateDenied
from tests import test_a_line_persistence as suite
from app.models.agent_entitlements import (EntitlementPolicyRow, OwnerEntitlementRow, PlanReleaseRow,
    GrantRootRow, WindowCounterRow, EntitlementAuditRow, ReservationAllocationRow)
from app.services.agent_entitlements import admin
from app.services.agent_entitlements.plans import build
from app.services.agent_entitlements.policy import EntitlementPolicy
from app.services.agent_entitlements.service import EntitlementError
from app.schemas.admin_plans import AssignPlans, PublishPlans


class FormalPlanTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = suite.ALinePersistenceTests.asyncSetUp
    asyncTearDown = suite.ALinePersistenceTests.asyncTearDown
    create_databases = suite.ALinePersistenceTests.create_databases
    submit = suite.ALinePersistenceTests.submit
    bind = suite.ALinePersistenceTests.bind
    claim = suite.ALinePersistenceTests.claim
    start_call = suite.ALinePersistenceTests.start_call
    finish_call = suite.ALinePersistenceTests.finish_call
    ingest = suite.ALinePersistenceTests.ingest
    prepare = suite.ALinePersistenceTests.prepare
    flush_usage = suite.ALinePersistenceTests.flush_usage

    async def formal_setup(self, plan='basic', risk=True):
        self.skill=SkillIdentity(schema_version=1,kind='skill',capability_id='skill:deep-research',
            resource_content_digest=digest('test-skill'),dependency_digests=[])
        identities=[self.identity,self.skill]
        self.catalog={'capabilities':[{'identity':i.model_dump(mode='json'),'version':digest(i.model_dump(mode='json'))} for i in identities]}
        self.bundle=build(self.catalog,release='test-20261120',model_budgets={'model:test/m1':dict(
            schema_version=1,input_basis='risk_assessed_utf8_v1',input_overhead_tokens=5,context_window_tokens=100,
            max_output_tokens=15,output_limit_semantics='completion_including_reasoning')},
                          risk_profile='test-risk-explicitly-approved' if risk else None)
        self.policies={p['plan_id']:EntitlementPolicy.model_validate(p) for p in self.bundle['policies']}
        async with self.backend() as db,db.begin():
            await db.execute(text('CREATE TABLE IF NOT EXISTS "user" (id TEXT PRIMARY KEY, email TEXT, "createdAt" TIMESTAMP WITH TIME ZONE)'))
            for id in ['test','other','new']:
                await db.execute(text('INSERT INTO "user" (id,email,"createdAt") VALUES (:id,:email,:created)'),
                    {'id':id,'email':id+'@test.invalid','created':datetime.now(timezone.utc)})
            body=PublishPlans(**self.bundle,operation_id='publish-test',reason='test approval',approval_ref='test-review',
                              risk_approval_ref='test-risk-approval' if risk else None)
            runtime={'models':[{'value':'test/m1','enabled':True}], 'skills':[{'name':'deep-research'}]}
            await admin.publish(db,body,'local-admin:test',runtime)
            owner=await db.get(OwnerEntitlementRow,'user:test')
            owner.policy_revision=self.policies[plan].policy_revision;owner.plan_id=plan
        self.policy=self.policies[plan]
        from agent_contracts.v2 import ModelCallBudgetRequest
        self.model_budget=ModelCallBudgetRequest(schema_version=1,basis='risk_assessed_utf8_v1',input_bytes=0,
            requested_output_tokens=15,model_max_output_tokens=15,model_context_window=100)

    async def mutate(self, plan='basic', action='assign', ids=None, op='assign-test', preview=False, initialize=False):
        body=AssignPlans(operation_id=op,reason='test reason',action=action,user_ids=ids or ['test'],
            plan_id=plan if action=='assign' else None,policy_revision=self.policies[plan].policy_revision if action=='assign' else None,
            preview=preview,initialize_only=initialize)
        async with self.backend() as db,db.begin():
            return await admin.assign(db,body,'local-admin:test')

    async def test_formal_admin_assignment_preview_batch_replay_and_upgrade(self):
        await self.formal_setup()
        preview=await self.mutate(ids=['new','missing'],preview=True)
        self.assertEqual([i['status'] for i in preview['items']],['failed','preview'])
        async with self.backend() as db:
            self.assertIsNone(await db.get(OwnerEntitlementRow,'user:new'))
        a=await self.mutate(ids=['new','missing'])
        b=await self.mutate(ids=['new','missing'])
        self.assertEqual(a,b)
        self.assertEqual(a['items'][1]['after']['plan_id'],'basic')
        for plan in ['pro','research','basic']:
            r=await self.mutate(plan=plan,op='upgrade-'+plan)
            self.assertEqual(r['items'][0]['status'],'success')
            self.assertEqual(r['items'][0]['after']['plan_id'],plan)
        r=await self.mutate(ids=['new'],initialize=True,op='preserve-new')
        self.assertEqual(r['items'][0]['reason'],'EXISTING_ASSIGNMENT_PRESERVED')
        async with self.backend() as db:
            rows=(await db.scalars(select(EntitlementAuditRow).where(EntitlementAuditRow.operation_id=='assign-test'))).all()
            self.assertEqual(len(rows),1)

    async def test_admin_http_policy_upload_publish_and_assignment(self):
        """Real routes and business transactions; only the Agent catalog is synthetic."""
        import json
        import os
        import httpx
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from app.api import admin_console

        await self.formal_setup()
        bundle = build(self.catalog, release='http-test',
            model_budgets=self.bundle['policies'][0]['model_budget_profiles'],
            risk_profile='test-risk-explicitly-approved')
        runtime = {'models': [{'value': 'test/m1', 'enabled': True}], 'skills': [{'name': 'deep-research'}]}

        @asynccontextmanager
        async def scope():
            async with self.backend() as db, db.begin():
                yield db

        app = FastAPI()
        app.include_router(admin_console.router)
        with patch.object(admin_console, 'session_scope', scope), patch.object(
                admin_console, 'get_capabilities', return_value=runtime), patch.dict(os.environ, {
                    'ENVIRONMENT': 'development', 'ADMIN_AUTH_MODE': 'local_password',
                    'ADMIN_AUTH_LOCAL_ONLY': 'true', 'ADMIN_LOCAL_USERNAME': 'shenzhi',
                    'ADMIN_LOCAL_PASSWORD': 'shenzhi-dev', 'ADMIN_SESSION_SECRET': 'test-secret-' * 4}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 123)),
                    base_url='http://localhost:3101', headers={'x-admin-request': '1'}) as browser:
                response = await browser.post('/api/v1/admin-console/auth/login',
                    json={'username': 'shenzhi', 'password': 'shenzhi-dev'})
                self.assertEqual(response.status_code, 200)
                # Same JSON payload that the existing file-upload UI submits.
                payload = json.loads(json.dumps(bundle))
                payload.update(operation_id='http-publish', reason='test upload',
                    approval_ref='test-policy-review', risk_approval_ref='test-risk-review')
                response = await browser.post('/api/v1/admin-console/plans/publish', json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                response = await browser.get('/api/v1/admin-console/plans')
                self.assertEqual(response.status_code, 200)
                self.assertTrue(all(p['published'] for p in response.json()['data']['items']))
                assignment = dict(operation_id='http-assign', reason='test assignment', user_ids=['new'],
                    plan_id='basic', policy_revision='basic-v1-http-test', preview=True)
                response = await browser.post('/api/v1/admin-console/entitlements/assign', json=assignment)
                self.assertEqual(response.json()['data']['items'][0]['status'], 'preview')
                async with self.backend() as db:
                    self.assertIsNone(await db.get(OwnerEntitlementRow, 'user:new'))
                assignment['preview'] = False
                for _ in range(2):
                    response = await browser.post('/api/v1/admin-console/entitlements/assign', json=assignment)
                    self.assertEqual(response.json()['data']['items'][0]['status'], 'success')
        async with self.backend() as db:
            self.assertEqual((await db.get(OwnerEntitlementRow, 'user:new')).policy_revision, 'basic-v1-http-test')
            rows = (await db.scalars(select(EntitlementAuditRow).where(
                EntitlementAuditRow.operation_id.in_(['http-publish', 'http-assign'])))).all()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row.principal == 'local-admin:shenzhi' for row in rows))

    async def test_formal_registration_never_auto_assigns(self):
        from app.services.agent_entitlements.defaults import initialize_free
        await self.formal_setup()
        async with self.backend() as db,db.begin():
            self.assertEqual(await initialize_free(db,'new'),0)
            self.assertIsNone(await db.get(OwnerEntitlementRow,'user:new'))
            with self.assertRaises(EntitlementError):await self.service.owner(db,'user:new')

    async def test_formal_per_call_no_task_ceiling_and_unknown_preserved(self):
        await self.formal_setup()
        await self.prepare()
        self.assertTrue(all(a.reserved_units==0 for a in self.grant.allocations))
        async with self.backend() as db:
            self.assertTrue(all(c.held==0 for c in (await db.scalars(select(WindowCounterRow))).all()))
        # Four full calls consume > the old reservation field (20) but can continue.
        for index in range(4):
            await self.start_call('formal-call-'+str(index))
            await self.flush_usage()
            usage,_=await self.finish_call(key='obs-'+str(index),tokens=7)
            await self.ingest(usage);await self.flush_usage()
        await self.start_call('formal-unknown');await self.flush_usage()
        usage,_=await self.finish_call(key='unknown',status='unknown')
        await self.ingest(usage);await self.flush_usage()
        async with self.backend() as db:
            counter=await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id=='daily-tokens'))
            self.assertEqual((counter.used,counter.held),(40,20))
        # Switching is explicitly blocked while a signed task remains open.
        r=await self.mutate(plan='pro',op='active-upgrade')
        self.assertEqual(r['items'][0]['reason'],'ACTIVE_GRANTS_REQUIRE_DRAIN')
        await self.mutate(action='disable',op='disable-test')
        async with self.backend() as db:
            with self.assertRaises(EntitlementError):await self.service.owner(db,'user:test')

    async def test_formal_deep_research_permission_at_control_and_submission(self):
        for plan in ['basic','pro','research']:
            if plan=='basic':await self.formal_setup()
            else:
                # New independent task per plan; prior root is only a test fixture.
                async with self.backend() as db,db.begin():
                    roots=(await db.scalars(select(GrantRootRow))).all()
                    for root in roots:root.status='closed'
                await self.mutate(plan=plan,op='change-to-'+plan)
                self.policy=self.policies[plan]
            if plan!='research':
                request=dict(owner_id='user:test',prompt='research',model='test/m1',skills=['deep-research'])
                with self.assertRaises(EntitlementError) as exc:
                    async with self.backend() as db,db.begin():
                        await self.service.authorize_submission(db,owner_id='user:test',client_key='forced-'+plan,request=request)
                self.assertEqual(exc.exception.reason,'CAPABILITY_NOT_AUTHORIZED')
            await self.submit(key='deep-'+plan);await self.bind();await self.claim(worker='worker-'+plan)
            for invocation in ['model_selected','forced']:
                body=CallIntent(**self.worker.model_dump(),call_id='skill-'+plan+invocation,logical_call_id='skill',
                    capability_identity=self.skill,invocation_mode=invocation,purpose='skill_activation',parent_call_id=None,
                    activation_id='activation',logical_attempt=1,transport_attempt=1,provider_id=None,
                    request_digest=digest('skill'),input_bound_evidence_ref=None,output_bound_evidence_ref=None,risk_profile=None)
                if plan!='research':
                    with self.assertRaises(GateDenied):
                        async with self.agent() as db,db.begin():await self.control.intent(db,self.run.run_id,body)
                else:
                    async with self.agent() as db,db.begin():await self.control.intent(db,self.run.run_id,body)
                    async with self.agent() as db:request=await self.control.permit_request(db,body.call_id)
                    async with self.backend() as db,db.begin():
                        response=await self.service.permit(db,request)
                        self.assertEqual(response['decision'],'authorized',response)
                    async with self.agent() as db,db.begin():
                        await self.control.attach_permit(db,body.call_id,response)
                        _,operation=await self.control.prepare_start(db,body.call_id,self.worker)
                    async with self.backend() as db,db.begin():
                        start=await self.service.start(db,response['permit']['permit_id'],operation)
                    async with self.agent() as db,db.begin():
                        receipt=await self.control.commit_start(db,body.call_id,self.worker,start)
                        self.assertTrue(receipt['may_send'])
                    break

    async def test_formal_quota_shared_across_revision_and_legacy_debt(self):
        await self.formal_setup()
        window=self.policy.rules[0].window('user:test',self.policy.policy_revision,datetime.now(timezone.utc))
        for plan in self.policies.values():
            self.assertEqual(plan.rules[0].window('user:test',plan.policy_revision,datetime.now(timezone.utc)).window_id,window.window_id)
        async with self.backend() as db,db.begin():
            db.add(WindowCounterRow(window_id=window.window_id,owner_id='user:test',rule_id='daily-tokens',window_ref=window.model_dump(mode='json'),limit_units=200000,used=199990,held=0))
        await self.prepare()
        # New task creation does not reserve the whole day; the first call still
        # fails if its reviewed bound cannot fit, before any provider execution.
        from agent_contracts.v2 import CallPermitRequest
        body=CallIntent(**self.worker.model_dump(),call_id='full',logical_call_id='full',capability_identity=self.identity,
            invocation_mode='internal',purpose='main',parent_call_id=None,activation_id=None,logical_attempt=1,
            transport_attempt=1,provider_id='test',request_digest=digest('full'),input_bound_evidence_ref=None,
            output_bound_evidence_ref=None,risk_profile='test-risk-explicitly-approved',model_budget=self.model_budget)
        async with self.agent() as db,db.begin():await self.control.intent(db,self.run.run_id,body)
        async with self.agent() as db:request=await self.control.permit_request(db,'full')
        async with self.backend() as db,db.begin():
            response=await self.service.permit(db,request)
            self.assertEqual(response['decision'],'authorized')
            self.assertEqual(response['permit']['model_budget']['output_tokens'],5)
        async with self.backend() as db:
            counter=await db.get(WindowCounterRow,window.window_id)
            self.assertEqual((counter.used,counter.held),(199990,10))

    async def test_formal_missing_risk_still_denies_model(self):
        await self.formal_setup(risk=False)
        await self.prepare()
        with self.assertRaises(AssertionError) as exc:
            await self.start_call('unapproved')
        self.assertIn('TOKEN_BOUND_UNPROVEN',str(exc.exception))

    async def test_formal_disable_restore_and_switch_drain(self):
        await self.formal_setup()
        await self.prepare()
        result=await self.mutate(plan='pro',op='active-switch')
        self.assertEqual(result['items'][0]['reason'],'ACTIVE_GRANTS_REQUIRE_DRAIN')
        result=await self.mutate(action='disable',op='disable-test')
        self.assertFalse(result['items'][0]['after']['enabled'])
        with self.assertRaises(AssertionError) as exc:await self.start_call('disabled')
        self.assertIn('GRANT_INACTIVE',str(exc.exception))
        await self.mutate(action='restore',op='restore-test')
        await self.start_call('restored')

    async def test_formal_upgrade_downgrade_keeps_used_and_held(self):
        await self.formal_setup()
        window=self.policy.rules[0].window('user:test',self.policy.policy_revision,datetime.now(timezone.utc))
        async with self.backend() as db,db.begin():
            db.add(WindowCounterRow(window_id=window.window_id,owner_id='user:test',rule_id='daily-tokens',
                window_ref=window.model_dump(mode='json'),limit_units=200000,used=12345,held=0))
            legacy=window.model_dump(mode='json');legacy['window_id']='legacy-day';legacy['rule_revision']='legacy-policy'
            db.add(WindowCounterRow(window_id='legacy-day',owner_id='user:test',rule_id='daily-tokens',
                window_ref=legacy,limit_units=200000,used=90,held=10))
        for plan in ['pro','research','basic']:
            result=await self.mutate(plan=plan,op='balance-'+plan)
            self.assertEqual(result['items'][0]['status'],'success')
            async with self.backend() as db:
                counter=await db.get(WindowCounterRow,window.window_id)
                self.assertEqual(counter.used,12345)
                self.assertEqual(counter.limit_units,self.policies[plan].rules[0].limit_units)
                self.assertEqual(await admin.daily_balance(db,'user:test',window),(12435,10))

    async def test_formal_partial_and_failed_usage_hold_real_budget(self):
        await self.formal_setup()
        await self.prepare();await self.start_call('partial');await self.flush_usage()
        usage,_=await self.finish_call(key='partial-observation',tokens=7,status='partial')
        await self.ingest(usage);await self.flush_usage()
        async with self.backend() as db:
            counter=await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id=='daily-tokens'))
            self.assertEqual((counter.used,counter.held),(7,13))
        usage,_=await self.finish_call(key='complete-observation',tokens=7)
        await self.ingest(usage);await self.flush_usage()
        async with self.backend() as db:
            counter=await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id=='daily-tokens'))
            self.assertEqual((counter.used,counter.held),(10,0))

    async def test_formal_publish_immutable_and_no_risk_forgery(self):
        await self.formal_setup()
        runtime={'models':[{'value':'test/m1','enabled':True}], 'skills':[{'name':'deep-research'}]}
        body=PublishPlans(**self.bundle,operation_id='publish-repeat',reason='review',approval_ref='test-approval')
        with self.assertRaises(EntitlementError) as exc:
            async with self.backend() as db,db.begin():await admin.publish(db,body,'local-admin:test',runtime)
        self.assertEqual(exc.exception.reason,'MODEL_RISK_APPROVAL_REQUIRED')
        body=body.model_copy(update={'risk_approval_ref':'test-risk-ref'})
        with self.assertRaises(EntitlementError) as exc:
            async with self.backend() as db,db.begin():await admin.publish(db,body,'local-admin:test',runtime)
        self.assertEqual(exc.exception.reason,'POLICY_REVISION_IMMUTABLE')

    async def test_dynamic_budget_has_no_16k_plan_cap_and_respects_remaining(self):
        from agent_contracts.execution_v2 import CallIntent
        from agent_contracts.v2 import ModelCallBudgetRequest
        await self.formal_setup()
        profile=self.policy.model_budget_profiles['model:test/m1'].model_copy(update={
            'max_output_tokens':32768,'context_window_tokens':128000})
        self.policy=self.policy.model_copy(update={'model_budget_profiles':{'model:test/m1':profile}})
        async with self.backend() as db,db.begin():
            row=await db.get(EntitlementPolicyRow,self.policy.policy_revision);row.payload=self.policy.model_dump(mode='json')
        await self.prepare()
        self.model_budget=ModelCallBudgetRequest(schema_version=1,basis='risk_assessed_utf8_v1',input_bytes=1000,
            requested_output_tokens=32768,model_max_output_tokens=32768,model_context_window=128000)
        await self.start_call('large-call')
        self.assertEqual(self.response['permit']['model_budget']['output_tokens'],32768)
        self.assertEqual(self.response['permit']['model_budget']['reserved_tokens'],33773)

    async def test_dynamic_missing_profile_or_input_room_fails_before_reservation(self):
        await self.formal_setup();await self.prepare()
        self.model_budget=self.model_budget.model_copy(update={'input_bytes':300000})
        with self.assertRaises(AssertionError) as exc:await self.start_call('no-input-room')
        self.assertIn('QUOTA_EXHAUSTED',str(exc.exception))
        async with self.backend() as db,db.begin():
            row=await db.get(EntitlementPolicyRow,self.policy.policy_revision)
            row.payload={**row.payload,'model_budget_profiles':{}}
        self.model_budget=self.model_budget.model_copy(update={'input_bytes':0})
        with self.assertRaises(AssertionError) as exc:await self.start_call('no-profile')
        self.assertIn('MODEL_BUDGET_UNCONFIGURED',str(exc.exception))
        async with self.backend() as db:
            counter=await db.scalar(select(WindowCounterRow).where(WindowCounterRow.rule_id=='daily-tokens'))
            self.assertEqual(counter.held,0)

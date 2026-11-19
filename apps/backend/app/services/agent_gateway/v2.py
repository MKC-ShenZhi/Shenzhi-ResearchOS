"""V2 Gateway reuses the HTTP boundary and persists before remote submission."""
import os

from sqlalchemy import select

from agent_contracts.canonical import digest, request_digest_v1
from agent_contracts.v2 import CallStartFact, TaskSubmissionV2
from agent_contracts.wire import TaskSubmissionWire
from app.core.database import session_scope
from app.models.agent_entitlements import (
    EntitlementPolicyRow, GrantRootRow, MeteringProfileRow, SubmissionRow, ObservationAdmissionRow,
)
from app.services.agent_entitlements.config import entitlement_service
from app.services.agent_entitlements.policy import EntitlementPolicy
from app.services.agent_entitlements.service import require, uid
from .client import AgentGateway


class AgentGatewayV2(AgentGateway):
    protocol_version = 2

    def __init__(self, **kwargs):
        kwargs.setdefault('token', os.getenv('AGENT_GATEWAY_TOKEN', '').strip())
        super().__init__(**kwargs)

    async def submit(self, payload, *, client_request_digest=None):
        request = TaskSubmissionWire.model_validate(payload)
        require(request.idempotency_key, 'IDEMPOTENCY_KEY_REQUIRED', 422)
        service = entitlement_service()
        # Only server-side deployments choose mode. Failure never falls back.
        mode = os.getenv('AGENT_V2_ADMISSION', 'disabled')
        async with session_scope() as db:
            original_profile = await db.scalar(select(MeteringProfileRow).where(
                MeteringProfileRow.owner_id == request.owner_id,
                MeteringProfileRow.client_key == request.idempotency_key))
            if original_profile:
                mode = original_profile.context
        if mode == 'observation_only':
            return await self.submit_observation(request, client_request_digest=client_request_digest)
        require(mode == 'authorized', 'AUTHORIZED_ADMISSION_DISABLED', 503)
        async with session_scope() as db:
            submission, grant = await service.authorize_submission(db, owner_id=request.owner_id,
                client_key=request.idempotency_key, request=request.model_dump(mode='json'), client_request_digest=client_request_digest)
            require(request.model is not None and any(p.capability_id == 'model:' + request.model for p in grant.capabilities),
                    'EXACT_MODEL_REQUIRED', 403)
            row = await db.get(EntitlementPolicyRow, grant.policy_revision)
            policy = EntitlementPolicy.model_validate(row.payload)
            envelope = TaskSubmissionV2(schema_version=1, metering_profile_id=submission.profile_id, metering_context='authorized',
                agent_audience=service.audience, owner_id=request.owner_id, request_digest=submission.request_digest,
                submission_id=submission.submission_id, budget_grant=grant, permission_snapshot=policy.permission_snapshot,
                call_bounds={r.rule_id: r.call_upper_bound for r in policy.rules}, request=request)
            submission_id = submission.submission_id
            profile = await db.get(MeteringProfileRow, submission.profile_id)
            known_task_id = profile.task_id
        if known_task_id:
            result = await self.task(known_task_id, request.owner_id)
            require(result.get('submission_id') == submission_id, 'AGENT_RESPONSE_INVALID', 502)
            if result.get('binding_status') == 'bound':
                if grant.revision > 1:
                    await self.request('POST', f'/internal/v2/grants/{grant.grant_id}/revisions', payload=grant.model_dump(mode='json'))
                return result
        result = await self.request('POST', '/internal/v2/tasks', payload=envelope.model_dump(mode='json'))
        require(result.get('schema_version') == 1 and result.get('metering_context') == 'authorized'
                and result.get('submission_id') == submission_id, 'AGENT_RESPONSE_INVALID', 502)
        async with session_scope() as db:
            submission = await db.get(SubmissionRow, submission_id)
            submission.status = 'bound' if result['binding_status'] == 'bound' else 'pending'
        return result

    async def submit_observation(self, request, *, client_request_digest=None):
        from sqlalchemy.exc import IntegrityError
        service = entitlement_service()
        revision = os.getenv('AGENT_OBSERVATION_ADMISSION_REVISION', '')
        async with session_scope() as db:
            query = select(ObservationAdmissionRow).where(ObservationAdmissionRow.owner_id == request.owner_id,
                                                          ObservationAdmissionRow.client_key == request.idempotency_key)
            admission = await db.scalar(query)
            if admission is None:
                require(os.getenv('AGENT_V2_ADMISSION') == 'observation_only' and revision,
                        'OBSERVATION_ADMISSION_UNAPPROVED', 503)
                try:
                    async with db.begin_nested():
                        profile = await service.prepare_profile(db, owner_id=request.owner_id,
                            request_digest=request_digest_v1(request.model_dump(mode='json')), admission_revision=revision,
                            client_key=request.idempotency_key)
                        admission = ObservationAdmissionRow(admission_id=uid(), owner_id=request.owner_id,
                            client_key=request.idempotency_key, profile_id=profile.profile_id,
                            request_digest=profile.request_digest, client_request_digest=client_request_digest,
                            request=request.model_dump(mode='json'))
                        db.add(admission)
                        await db.flush()
                except IntegrityError:
                    admission = await db.scalar(query)
                    require(admission is not None, 'ADMISSION_CONFLICT')
            require(admission.request_digest == request_digest_v1(request.model_dump(mode='json')) and
                    admission.request == request.model_dump(mode='json') and
                    (client_request_digest is None or admission.client_request_digest == client_request_digest), 'IDEMPOTENCY_CONFLICT')
            envelope = TaskSubmissionV2(schema_version=1, metering_profile_id=admission.profile_id, metering_context='observation_only',
                agent_audience=service.audience, owner_id=request.owner_id, request_digest=admission.request_digest,
                submission_id=None, budget_grant=None, permission_snapshot=None, call_bounds={}, request=request)
        result = await self.request('POST', '/internal/v2/tasks', payload=envelope.model_dump(mode='json'))
        require(result.get('schema_version') == 1 and result.get('metering_context') == 'observation_only'
                and result.get('metering_profile_id') == envelope.metering_profile_id, 'AGENT_RESPONSE_INVALID', 502)
        return result

    async def recover_submission(self, owner, client_key):
        async with session_scope() as db:
            submission = await db.scalar(select(SubmissionRow).where(
                SubmissionRow.owner_id == owner, SubmissionRow.client_key == client_key))
            if submission is None:
                submission = await db.scalar(select(ObservationAdmissionRow).where(
                    ObservationAdmissionRow.owner_id == owner, ObservationAdmissionRow.client_key == client_key))
            require(submission is not None, 'SUBMISSION_NOT_FOUND', 404)
            request = dict(submission.request)
            is_observation = isinstance(submission, ObservationAdmissionRow)
        if is_observation:
            # Existing A1 facts/mode survive an A2 admission switch; no new profile.
            return await self.submit_observation(TaskSubmissionWire.model_validate(request))
        return await self.submit(request)

    async def task(self, task_id, owner):
        return await self.request('GET', f'/internal/v2/tasks/{task_id}', params={'owner_id': owner})

    async def run(self, run_id, owner):
        return await self.request('GET', f'/internal/v2/runs/{run_id}', params={'owner_id': owner})

    async def task_runs(self, task_id, owner):
        return (await self.request('GET', f'/internal/v2/tasks/{task_id}/runs', params={'owner_id': owner}))['run_ids']

    async def events(self, run_id, owner, after_seq):
        return (await self.request('GET', f'/internal/v2/runs/{run_id}/events',
                                   params={'owner_id': owner, 'after_seq': after_seq}))['events']

    async def cancel(self, task_id, owner):
        return await self.request('POST', f'/internal/v2/tasks/{task_id}/cancel', params={'owner_id': owner})

    async def steer(self, run_id, owner, message):
        return await self.request('POST', f'/internal/v2/runs/{run_id}/steer',
                                   payload={'schema_version': 1, 'owner_id': owner, 'text': message})

    async def start_fact(self, task_id, call_id):
        # Only the configured Agent environment is queried, never an event URL.
        reader = AgentGateway(base_url=self.base_url, token=os.getenv('AGENT_FACT_READER_TOKEN', '').strip(), transport=self.transport)
        return CallStartFact.model_validate(await reader.request('GET', f'/internal/v2/tasks/{task_id}/call-facts/{call_id}'))

    async def usage(self, task_id, owner):
        from app.services.agent_entitlements.usage import UsageSettlement
        async with session_scope() as db:
            return await UsageSettlement(entitlement_service()).task_usage(db, task_id=task_id, owner_id=owner)

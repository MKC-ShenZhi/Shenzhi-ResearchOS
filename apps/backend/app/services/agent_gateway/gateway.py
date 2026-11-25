"""Agent communication Gateway over the shared authenticated HTTP client."""
import base64
import os

from sqlalchemy import select

from agent_contracts import (
    AgentConfigWire, SessionFileReadRequestWire, SessionFileReadResponseWire,
    TaskRunsResponseWire,
    WorkspaceClaimCommitResponseWire, WorkspaceClaimPrepareResponseWire,
    WorkspaceClaimRequestWire, WorkspaceCreateRequestWire, WorkspaceCreateResponseWire,
    WorkspaceFileWriteRequestWire, WorkspaceFileWriteResponseWire,
)
from agent_contracts.canonical import digest, request_digest_v1
from agent_contracts.v2 import CallStartFact, TaskSubmissionV2
from agent_contracts.wire import TaskSubmissionWire
from app.core.database import session_scope
from app.core.errors import BusinessError
from app.models.agent_entitlements import (
    EntitlementPolicyRow, GrantRootRow, MeteringProfileRow, SubmissionRow, ObservationAdmissionRow,
)
from app.services.agent_entitlements.config import entitlement_service
from app.services.agent_entitlements.policy import EntitlementPolicy
from app.services.agent_entitlements.service import require, uid
from .client import AgentHttpClient


class AgentGateway(AgentHttpClient):
    def __init__(self, **kwargs):
        kwargs.setdefault('token', os.getenv('AGENT_GATEWAY_TOKEN', '').strip())
        super().__init__(**kwargs)

    def service_gateway(self):
        """V2 shared capabilities use the isolated service role credential."""
        return AgentHttpClient(base_url=self.base_url, token=os.getenv('AGENT_SERVICE_TOKEN', '').strip(),
                               transport=self.transport)

    async def config(self):
        result = await self.service_gateway().request('GET', '/internal/v2/config')
        return AgentConfigWire.model_validate(result).model_dump(mode='json')

    async def create_workspace(self, owner):
        body = WorkspaceCreateRequestWire(owner_id=owner)
        result = await self.service_gateway().request('POST', '/internal/v2/workspaces',
                                                       payload=body.model_dump(mode='json'))
        return WorkspaceCreateResponseWire.model_validate(result).model_dump(mode='json')

    async def prepare_workspace_claim(self, source_owner, target_owner, session_ids):
        body = WorkspaceClaimRequestWire(source_owner=source_owner, target_owner=target_owner,
                                         session_ids=session_ids)
        result = await self.service_gateway().request('POST', '/internal/v2/workspaces/claim/prepare',
                                                       payload=body.model_dump(mode='json'))
        return WorkspaceClaimPrepareResponseWire.model_validate(result).model_dump(mode='json')

    async def commit_workspace_claim(self, source_owner, target_owner, session_ids):
        body = WorkspaceClaimRequestWire(source_owner=source_owner, target_owner=target_owner,
                                         session_ids=session_ids)
        result = await self.service_gateway().request('POST', '/internal/v2/workspaces/claim/commit',
                                                       payload=body.model_dump(mode='json'))
        return WorkspaceClaimCommitResponseWire.model_validate(result).model_dump(mode='json')

    async def write_workspace_file(self, workspace_id, owner, path, content):
        body = WorkspaceFileWriteRequestWire(owner_id=owner, workspace_id=workspace_id, path=path,
            content_base64=base64.b64encode(content).decode('ascii'))
        result = await self.service_gateway().request('POST', f'/internal/v2/workspaces/{workspace_id}/files',
                                                       payload=body.model_dump(mode='json'))
        return WorkspaceFileWriteResponseWire.model_validate(result).model_dump(mode='json')

    async def read_session_file(self, owner, session_id, path):
        query = SessionFileReadRequestWire(owner_id=owner, path=path)
        result = await self.service_gateway().request('GET', f'/internal/v2/sessions/{session_id}/files',
                                                       params=query.model_dump(mode='json'))
        response = SessionFileReadResponseWire.model_validate(result)
        try:
            content = base64.b64decode(response.content_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise BusinessError(20004, 'Agent 文件响应无效', 502) from exc
        return content, response.media_type

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
        if original_profile is None and request.owner_id.startswith('user:'):
            require(mode == 'authorized', 'AUTHORIZED_ADMISSION_DISABLED', 503)
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
            # A response error after the Task may exist is indeterminate: never
            # turn it into a definitive authorization rejection.
            if result.get('submission_id') != submission_id:
                raise BusinessError(20004, 'AGENT_RESPONSE_INVALID', 502)
            if result.get('binding_status') == 'bound':
                if grant.revision > 1:
                    await self.request('POST', f'/internal/v2/grants/{grant.grant_id}/revisions', payload=grant.model_dump(mode='json'))
                return result
        result = await self.request('POST', '/internal/v2/tasks', payload=envelope.model_dump(mode='json'))
        if not (result.get('schema_version') == 1 and result.get('metering_context') == 'authorized'
                and result.get('submission_id') == submission_id):
            raise BusinessError(20004, 'AGENT_RESPONSE_INVALID', 502)
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
        if not (result.get('schema_version') == 1 and result.get('metering_context') == 'observation_only'
                and result.get('metering_profile_id') == envelope.metering_profile_id):
            raise BusinessError(20004, 'AGENT_RESPONSE_INVALID', 502)
        return result

    async def recover_submission(self, owner, client_key, *, allow_missing=False):
        async with session_scope() as db:
            submission = await db.scalar(select(SubmissionRow).where(
                SubmissionRow.owner_id == owner, SubmissionRow.client_key == client_key))
            if submission is None:
                submission = await db.scalar(select(ObservationAdmissionRow).where(
                    ObservationAdmissionRow.owner_id == owner, ObservationAdmissionRow.client_key == client_key))
            if submission is None:
                # Session recovery may distinguish a crash before admission
                # from a missing key in operator or product recovery flows.
                if not allow_missing:
                    raise BusinessError(20004, 'SUBMISSION_NOT_FOUND', 404)
                return None
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
        response = await self.request('GET', f'/internal/v2/tasks/{task_id}/runs', params={'owner_id': owner})
        return TaskRunsResponseWire.model_validate(response).run_ids

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
        reader = AgentHttpClient(base_url=self.base_url, token=os.getenv('AGENT_FACT_READER_TOKEN', '').strip(), transport=self.transport)
        return CallStartFact.model_validate(await reader.request('GET', f'/internal/v2/tasks/{task_id}/call-facts/{call_id}'))

    async def close_facts(self, task_id):
        reader = AgentHttpClient(base_url=self.base_url, token=os.getenv('AGENT_FACT_READER_TOKEN', '').strip(), transport=self.transport)
        return await reader.request('GET', f'/internal/v2/tasks/{task_id}/close-facts')

    async def usage(self, task_id, owner):
        from app.services.agent_entitlements.usage import UsageSettlement
        async with session_scope() as db:
            return await UsageSettlement(entitlement_service()).task_usage(db, task_id=task_id, owner_id=owner)

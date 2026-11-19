"""Protocol candidates: round trips, nulls, identity, canonical bytes and JWS."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from agent_contracts.canonical import canonical_json_v1, digest, parse_canonical
from agent_contracts.v2 import CallStartFact, ModelIdentity, UsageDelta, WindowRef


def model_identity():
    return ModelIdentity(schema_version=1, kind='model', capability_id='model:test/m1', provider_id='test',
        registry_model_id='test/m1', upstream_model='m1', configuration_release_digest=digest('release'), dependency_digests=[])


def started_fact(**changes):
    identity = model_identity()
    now = datetime.now(timezone.utc)
    raw = dict(schema_version=1, agent_audience='test-agent', task_id='task', run_id='run', execution_id='execution',
        call_id='call', logical_call_id='logical', metering_profile_id='profile', metering_context='observation_only',
        submission_id_source='agent_observation', submission_id='obs:submission', owner_id='user:test',
        control_attestation_id='attestation', started_at=now, capability_id=identity.capability_id,
        capability_version=digest(identity.model_dump(mode='json')), capability_identity_profile='capability_identity_v1',
        capability_identity=identity.model_dump(mode='json'), invocation_mode='internal', purpose='main',
        parent_call_id=None, activation_id=None, grant_id=None, grant_revision=None, reservation_id=None, permit_id=None,
        fact_kind='started', start_record_id='start', recorded_at=now)
    raw.update(changes)
    raw = parse_canonical(canonical_json_v1(raw))
    return CallStartFact(**raw, start_record_digest=digest(raw))


def delta(**changes):
    from agent_contracts.v2 import CallIdentity
    fact = started_fact()
    raw = {k: fact.model_dump(mode='json')[k] for k in CallIdentity.model_fields}
    raw.update(measurement_id='measurement', observation_revision=1, supersedes_measurement_id=None,
        logical_attempt=1, transport_attempt=1, provider_id='test', provider_request_id=None,
        phase='started', outcome='in_progress', prompt_tokens=None, completion_tokens=None,
        usage_status='unknown', usage_source=None, missing_reason='pending', attempted_units=1,
        successful_units=None, ended_at=None, observed_at=fact.started_at, task_usage_sequence=1)
    raw.update(changes)
    return UsageDelta.model_validate(raw)


class ProtocolV2Tests(unittest.TestCase):
    def test_roundtrip_keeps_explicit_null_and_unknown(self):
        value = delta()
        self.assertEqual(value, UsageDelta.model_validate_json(value.model_dump_json()))
        self.assertIsNone(json.loads(value.model_dump_json())['prompt_tokens'])
        raw = value.model_dump(mode='json')
        del raw['prompt_tokens']
        with self.assertRaises(ValidationError):
            UsageDelta.model_validate(raw)

    def test_unknown_schema_extra_and_unsafe_units_rejected(self):
        for change in ({'schema_version': 2}, {'schema_version': True}, {'lease_token': 1}, {'prompt_tokens': -1},
                       {'task_usage_sequence': True}, {'attempted_units': 2**53}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                UsageDelta.model_validate(dict(delta().model_dump(mode='json'), **change))

    def test_usage_and_outcome_are_orthogonal(self):
        value = delta(phase='completed', outcome='failed', prompt_tokens=2, completion_tokens=3,
                      usage_status='measured', usage_source='provider_usage')
        self.assertEqual(value.outcome, 'failed')
        with self.assertRaises(ValidationError):
            delta(usage_status='measured')
        self.assertIsNone(delta(prompt_tokens=2, usage_status='partial', usage_source='provider_usage').completion_tokens)

    def test_mode_namespace_and_revision_chain_enforced(self):
        for change in ({'metering_context':'authorized'}, {'submission_id':'formal'},
                       {'grant_id':'grant'}, {'observation_revision':2}, {'capability_version':digest('wrong')}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                delta(**change)
        self.assertEqual(delta(call_id='attempt2', logical_call_id='logical').logical_call_id, 'logical')

    def test_start_digest_is_immutable(self):
        fact = started_fact()
        self.assertEqual(fact.start_record_digest, fact.computed_digest())
        with self.assertRaises(ValidationError):
            CallStartFact.model_validate(dict(fact.model_dump(mode='json'), run_id='other'))

    def test_canonical_vectors(self):
        self.assertEqual(canonical_json_v1({'文': [None, True], 'a': 2}), '{"a":2,"文":[null,true]}'.encode())
        self.assertEqual(canonical_json_v1(datetime(2026,1,1,tzinfo=timezone.utc)), b'"2026-01-01T00:00:00.000Z"')
        for raw in (b'{"a":1,"a":2}', b'{ "a":1}', b'{"x":NaN}', b'\xef\xbb\xbf{}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_canonical(raw)
        for value in (float('inf'), 1.1, 2**53, datetime(2026,1,1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_json_v1(value)

    def test_window_ref_does_not_forge_rolling_bounds(self):
        now = datetime.now(timezone.utc)
        raw = dict(schema_version=1, window_id='window', rule_revision='policy', window_type='rolling', accounting_basis='trusted_start',
                   start=None, end=None, duration_seconds=18000, timezone=None, anchor=None, ledger_ref='ledger')
        self.assertEqual(WindowRef(**raw).duration_seconds, 18000)
        with self.assertRaises(ValidationError):
            WindowRef(**dict(raw, start=now, end=now+timedelta(hours=5)))

    def test_version_is_required_even_for_first_schema(self):
        raw=delta().model_dump(mode='json')
        del raw['schema_version']
        with self.assertRaises(ValidationError):
            UsageDelta.model_validate(raw)

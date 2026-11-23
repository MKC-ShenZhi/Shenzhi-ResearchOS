"""Build the user-approved V1 demo policy from actual Worker identities.

Risk approval is deliberately separate from the approved Free quota. Omitting
it installs a valid assignment but model permits still fail TOKEN_BOUND_UNPROVEN.
"""
import argparse
import json
from pathlib import Path

from agent_contracts.canonical import digest
from agent_contracts.v2 import ModelIdentity, ToolIdentity, SkillIdentity
from .policy import EntitlementPolicy

DEFINITION = json.loads((Path(__file__).resolve().parents[2] / 'data/agent_free_demo_policy.json').read_text(encoding='utf-8'))
REVISION = DEFINITION['policy_revision']


def build(capabilities, *, risk_profile=None, risk_approval_ref=None):
    if bool(risk_profile) != bool(risk_approval_ref):
        raise ValueError('A model risk profile requires its separate approval reference')
    permissions = []
    models = 0
    for entry in capabilities['capabilities']:
        raw = entry['identity']
        cls = {'model': ModelIdentity, 'tool': ToolIdentity, 'skill': SkillIdentity}[raw['kind']]
        identity = cls.model_validate(raw)
        if entry['version'] != digest(identity.model_dump(mode='json')):
            raise ValueError('Capability digest mismatch')
        if identity.capability_id == 'tool:run_command':
            raise ValueError('Shell is excluded from the Free policy')
        kind = raw['kind']
        models += kind == 'model'
        permissions.append(dict(schema_version=1, capability_id=identity.capability_id, capability_version=entry['version'],
            invocation_modes=['internal'] if kind == 'model' else ['model_selected'] if kind == 'tool' else ['forced', 'model_selected'],
            purposes=['main', 'summary'] if kind == 'model' else ['tool'] if kind == 'tool' else ['skill_activation'],
            max_attempts=None, dependency_versions={}))
    if not models or len({p['capability_id'] for p in permissions}) != len(permissions):
        raise ValueError('Public model identities required; capability IDs must be unique')
    def rule(rule_id, metric, unit, purpose, *, charging):
        return dict(schema_version=1, rule_id=rule_id, metric=metric, unit=unit, capability_id=None,
            purpose=purpose, limit_units=DEFINITION['token_limit'] if charging else 0,
            reservation_units=DEFINITION['task_reservation'] if charging else 0,
            call_upper_bound=DEFINITION['model_call_upper_bound'] if charging else 0,
            accounting_basis='trusted_start' if charging else 'free', window_type=DEFINITION['window_type'],
            duration_seconds=None, timezone=DEFINITION['timezone'], anchor=None)
    policy = EntitlementPolicy.model_validate(dict(schema_version=1, policy_revision=REVISION, plan_id=DEFINITION['plan_id'],
        permission_snapshot=dict(schema_version=1, permission_snapshot_id=REVISION + ':snapshot',
            policy_revision=REVISION, catalog_revision=digest(capabilities), capabilities=permissions),
        rules=[rule('daily-tokens', 'tokens', 'token', 'all', charging=True),
               rule('tools-free', 'attempted_units', 'call', 'tool', charging=False),
               rule('skills-free', 'attempted_units', 'activation', 'skill_activation', charging=False)],
        **{key: DEFINITION[key] for key in ('grant_ttl_seconds', 'permit_ttl_seconds', 'start_ttl_seconds',
                                          'conservative_clock_skew_ms', 'token_scope')},
        missing_usage_strategy='hold_and_reconcile',
        overage_strategy='record_and_block', unused_release_strategy='sealed_complete_only',
        model_risk_profile=risk_profile, disable_scope='new_submissions', emergency_scope='grant_root'))
    return dict(policy=policy.model_dump(mode='json'), approved=True, test_only=False,
        approval_ref=DEFINITION['approval_ref'], principal='operator:free-demo', operation_id=REVISION,
        risk_approval_ref=risk_approval_ref)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capabilities', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--risk-profile')
    parser.add_argument('--risk-approval-ref')
    args = parser.parse_args()
    payload = build(json.loads(Path(args.capabilities).read_text(encoding='utf-8')),
                    risk_profile=args.risk_profile, risk_approval_ref=args.risk_approval_ref)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

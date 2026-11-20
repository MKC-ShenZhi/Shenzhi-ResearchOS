"""Fixed product plans built from an actual reviewed Worker capability export.

No default model risk approval; the operator supplies evidence separately.
"""
import argparse
import json
from pathlib import Path
from agent_contracts.canonical import digest
from agent_contracts.v2 import ModelIdentity, ToolIdentity, SkillIdentity
from .policy import EntitlementPolicy

PLANS = {'basic': ('Basic 基础版', 200000), 'pro': ('Pro 专业版', 1000000), 'research': ('Research 研究版', 3000000)}
POOL = 'formal-daily-tokens-v1'


def build(capabilities, *, release, model_budgets=None, risk_profile=None):
    if not release:
        raise ValueError('release required')
    identities = []
    for entry in capabilities['capabilities']:
        raw = entry['identity']
        cls = {'model': ModelIdentity, 'tool': ToolIdentity, 'skill': SkillIdentity}[raw['kind']]
        identity = cls.model_validate(raw)
        if entry['version'] != digest(identity.model_dump(mode='json')):
            raise ValueError('capability digest conflict')
        identities.append((identity, entry['version']))
    ids = [i.capability_id for i, _ in identities]
    if len(ids) != len(set(ids)) or not any(i.kind == 'model' for i, _ in identities) or 'skill:deep-research' not in ids:
        raise ValueError('unique real model and deep-research identities required')
    if 'tool:run_command' in ids:
        raise ValueError('shell is outside this product release')
    model_ids = {i.capability_id for i, _ in identities if i.kind == 'model'}
    if risk_profile and not model_budgets:
        raise ValueError('model risk profile requires at least one reviewed model budget')
    # A model without a budget remains denied by Permit. Do not require
    # enabling unrelated models just to configure one supported model.
    if set(model_budgets or {}) - model_ids:
        raise ValueError('model budget profile has an unknown model identity')
    policies = []
    for plan, (_, limit) in PLANS.items():
        revision = f'{plan}-v1-{release}'
        permissions = [dict(schema_version=1, capability_id=i.capability_id, capability_version=v,
            invocation_modes=['internal','model_selected','forced','explicit_user'],
            purposes=['main','summary'] if i.kind == 'model' else ['tool'] if i.kind == 'tool' else ['skill_activation'],
            max_attempts=None, dependency_versions={}) for i, v in identities
            if plan == 'research' or i.capability_id != 'skill:deep-research']
        rules = [dict(schema_version=1, rule_id='daily-tokens', metric='tokens', unit='token', capability_id=None,
            purpose='all', limit_units=limit, reservation_units=0, call_upper_bound=0,
            accounting_basis='trusted_start', window_type='natural', duration_seconds=None,
            timezone='Asia/Shanghai', anchor=None, quota_pool=POOL)]
        for rule_id, unit, purpose in [('tools-free','call','tool'),('skills-free','activation','skill_activation')]:
            rules.append(dict(schema_version=1, rule_id=rule_id, metric='attempted_units', unit=unit,
                capability_id=None, purpose=purpose, limit_units=0, reservation_units=0, call_upper_bound=0,
                accounting_basis='free', window_type='natural', duration_seconds=None, timezone='Asia/Shanghai', anchor=None))
        policy = EntitlementPolicy.model_validate(dict(schema_version=1, reservation_mode='per_call', dynamic_model_budget=True,
            model_budget_profiles=model_budgets or {}, policy_revision=revision,
            plan_id=plan, permission_snapshot=dict(schema_version=1, permission_snapshot_id=revision+':snapshot',
                policy_revision=revision, catalog_revision=digest(capabilities), capabilities=permissions), rules=rules,
            grant_ttl_seconds=7200, permit_ttl_seconds=120, start_ttl_seconds=30, conservative_clock_skew_ms=1000,
            token_scope='prompt_plus_completion', missing_usage_strategy='hold_and_reconcile', overage_strategy='record_and_block',
            unused_release_strategy='sealed_complete_only', model_risk_profile=risk_profile,
            disable_scope='every_start', emergency_scope='grant_root'))
        policies.append(policy.model_dump(mode='json'))
    return {'policies':policies, 'capabilities':capabilities}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capabilities',required=True); p.add_argument('--release',required=True)
    p.add_argument('--model-budgets', help='Reviewed per-model deployment risk constraints JSON'); p.add_argument('--risk-profile')
    p.add_argument('--previous-bundle', help='Reuse budget/risk settings from an existing formal bundle; no database writes')
    p.add_argument('--input-bytes-per-token', type=int, choices=[1, 2],
                   help='Explicit input risk estimate: 1 preserves historical behavior, 2 reduces byte-based reservation')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    previous = None
    if a.previous_bundle:
        previous = EntitlementPolicy.model_validate(
            json.loads(Path(a.previous_bundle).read_text(encoding='utf-8'))['policies'][0])
    budgets = ({k:v.model_dump(mode='json') for k,v in previous.model_budget_profiles.items()}
               if previous else {})
    if a.model_budgets:
        budgets.update(json.loads(Path(a.model_budgets).read_text(encoding='utf-8')))
    if a.input_bytes_per_token is not None:
        for profile in budgets.values():
            profile['input_bytes_per_token'] = a.input_bytes_per_token
    risk_profile = a.risk_profile if a.risk_profile is not None else previous.model_risk_profile if previous else None
    if not risk_profile or not budgets:
        p.error('model_risk_profile/model_budget_profiles missing: provide --risk-profile and --model-budgets; '
                '--previous-bundle does not create missing risk configuration')
    bundle=build(json.loads(Path(a.capabilities).read_text(encoding='utf-8')),release=a.release,
                 model_budgets=budgets, risk_profile=risk_profile)
    Path(a.output).write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')

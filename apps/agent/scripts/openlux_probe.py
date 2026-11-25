"""Opt-in OpenLux probe. Reuses AutoDL's T0-T7 checks; never registers models.

Run from apps/agent with uv run --env-file .env python scripts/openlux_probe.py --list-only
then pass 3-5 exact IDs from that directory for low-volume compatibility checks.
"""
import argparse
import importlib.util
import json
from pathlib import Path

import httpx

from agent_app.integrations.llm.resolver import load_registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='*')
    parser.add_argument('--list-only', action='store_true')
    args = parser.parse_args()
    provider = load_registry().providers['openlux']
    if not provider.configured:
        print(json.dumps({'stop_reason': '缺少 OPENLUX_API_KEY'}, ensure_ascii=False))
        return 2
    source = Path(__file__).resolve().parents[2] / 'backend/scripts/autodl_probe.py'
    spec = importlib.util.spec_from_file_location('compat_probe', source)
    probe_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe_module)
    key = provider.key.get_secret_value()
    with httpx.Client(timeout=httpx.Timeout(120, connect=10), follow_redirects=False) as client:
        report = probe_module.run(probe_module.Probe(client, provider.spec.base_url, key),
                                  args.models, list_only=args.list_only, require_v41=False)
    print(probe_module.redact(json.dumps(report, ensure_ascii=False, indent=2), key))
    return 2 if report.get('stop_reason') else 0


if __name__ == '__main__':
    raise SystemExit(main())

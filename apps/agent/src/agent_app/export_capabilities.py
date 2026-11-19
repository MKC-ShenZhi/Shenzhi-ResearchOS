"""Export current product identities offline; never invoke models or tools.

Run on the exact deployed Worker build with its environment and credentials.
The output contains identities/digests only, never credentials or endpoints.
"""
import argparse
import json
import uuid
from pathlib import Path

from agent_contracts.canonical import digest
from agent_app.application.composition import build_runtime
from agent_app.execution.metering import model_identity, tool_identity, skill_identity
from agent_app.extensions.skills import default_store
from agent_app.integrations.llm.resolver import load_registry


def export():
    registry = load_registry()
    identities = [model_identity(registry.resolve_model(model['value'], 'agent'))
                  for model in registry.public_models('agent') if model['enabled']]
    if not identities:
        raise ValueError('No configured public Agent models; cannot create an approved snapshot')
    # Same assembly as the product Worker, with shell disabled. The empty export
    # workspace contains no user data. Runtime construction sends no requests.
    runtime = build_runtime(owner='system:policy-export', session_id='export-' + uuid.uuid4().hex,
                            mode='deep', allow_shell=False)
    identities.extend(tool_identity(tool) for tool in runtime.registry.tools.values())
    store = default_store()
    identities.extend(skill_identity(store.get(name)) for name in store.names()
                      if not store.get(name).disable_model_invocation)
    if any(identity.capability_id == 'tool:run_command' for identity in identities):
        raise ValueError('Shell cannot be exported for Free users')
    return {'capabilities': [dict(identity=identity.model_dump(mode='json'),
                                   version=digest(identity.model_dump(mode='json'))) for identity in identities]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(export(), ensure_ascii=False, indent=2), encoding='utf-8')

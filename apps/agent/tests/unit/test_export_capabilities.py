"""Capability export uses actual product assembly without any network calls."""
import os
from unittest.mock import patch

from agent_contracts.canonical import digest
from agent_app.export_capabilities import export
from agent_app.extensions import workspace


def test_public_capability_export_is_offline_and_has_no_shell(tmp_path):
    with patch.dict(os.environ, {
        'DEEPSEEK_API_KEY': 'test-only',
        'DASHSCOPE_API_KEY': '', 'ZHIPU_API_KEY': '',
        'AGENT_MODEL_ROUTE_REVISION': 'test-export-route',
        'AGENT_TOOL_CONFIGURATION_RELEASE': 'test-export-tools',
    }, clear=True), patch.object(workspace, 'WORKSPACE_ROOT', tmp_path), \
         patch('httpx.AsyncClient.send', side_effect=AssertionError('export must stay offline')), \
         patch('httpx.Client.send', side_effect=AssertionError('export must stay offline')):
        manifest = export()
    entries = manifest['capabilities']
    assert any(entry['identity']['kind'] == 'model' for entry in entries)
    assert any(entry['identity']['kind'] == 'skill' for entry in entries)
    assert any(entry['identity']['capability_id'] == 'tool:read_file' for entry in entries)
    assert not any(entry['identity']['capability_id'] == 'tool:run_command' for entry in entries)
    assert len({entry['identity']['capability_id'] for entry in entries}) == len(entries)
    assert all(entry['version'] == digest(entry['identity']) for entry in entries)


def test_key_only_export_matches_registry_and_fixed_model_identity(tmp_path):
    from agent_app.integrations.llm.resolver import load_registry
    from agent_app.execution.metering import model_identity

    env = {'AUTODL_API_KEY': 'test-only', 'DEEPSEEK_API_KEY': 'test-deep',
           'AGENT_MODEL_ROUTE_REVISION': 'reviewed-route',
           'AGENT_TOOL_CONFIGURATION_RELEASE': 'reviewed-tools'}
    with patch.dict(os.environ, env, clear=True), patch.object(workspace, 'WORKSPACE_ROOT', tmp_path), \
         patch('httpx.AsyncClient.send', side_effect=AssertionError('must stay offline')):
        registry = load_registry()
        before = model_identity(registry.resolve_model('deepseek/deepseek-chat', 'agent'))
        manifest = export()
        entries = [e for e in manifest['capabilities'] if e['identity']['kind'] == 'model']
        assert {e['identity']['registry_model_id'] for e in entries} == {
            m['value'] for m in registry.public_models('agent') if m['enabled']}
        with patch.dict(os.environ, {'DASHSCOPE_API_KEY': 'extra-key'}):
            after = model_identity(load_registry().resolve_model('deepseek-chat', 'agent'))
        assert before == after
        assert all('test-only' not in str(e) and 'test-deep' not in str(e) for e in entries)

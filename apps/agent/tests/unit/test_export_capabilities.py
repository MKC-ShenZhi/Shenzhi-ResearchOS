"""Capability export uses actual product assembly without any network calls."""
import os
from unittest.mock import patch

from agent_contracts.canonical import digest
from agent_app.export_capabilities import export
from agent_app.extensions import workspace


def test_public_capability_export_is_offline_and_has_no_shell(tmp_path):
    with patch.dict(os.environ, {
        'DEEPSEEK_API_KEY': 'test-only', 'DEEPSEEK_MODEL': 'deepseek-chat',
        'DASHSCOPE_API_KEY': '', 'ZHIPU_API_KEY': '',
        'AGENT_MODEL_ROUTE_REVISION': 'test-export-route',
        'AGENT_TOOL_CONFIGURATION_RELEASE': 'test-export-tools',
    }), patch.object(workspace, 'WORKSPACE_ROOT', tmp_path), \
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

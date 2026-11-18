"""Offline simulation uses ordinary events, reports and owner-bound workspaces."""
import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from agent_contracts import AgentConfigWire, ExecutionReportWire

from agent_app.demo_worker import DEMO_WARNING, DemoRuntime
from agent_app.execution.types import RunChannel
from agent_app.extensions.workspace import read_session_file
from agent_app.main import app
from agent_app.worker.host import report_payload, run_worker_forever


class DemoWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_matches_file_and_shared_contract_without_providers(self):
        with tempfile.TemporaryDirectory() as root, patch.dict('os.environ', {'AGENT_WORKSPACE_ROOT': root}), \
                patch('agent_app.demo_worker.asyncio.sleep', new_callable=AsyncMock):
            runtime = DemoRuntime(owner='anon:demo', session_id='ses_' + 'a' * 32,
                                  mode='deep', model='demo/m1')
            events = []
            result = await runtime.run('对比 LoRA 和 QLoRA', history=[], stop=asyncio.Event(),
                                       on_event=events.append, channel=RunChannel())
            self.assertEqual(result.status, 'done')
            self.assertIn(DEMO_WARNING, result.output['report'])
            content, _ = read_session_file('anon:demo', 'ses_' + 'a' * 32, result.output['report_path'])
            self.assertEqual(content.decode('utf-8'), result.output['report'])
            self.assertEqual([event.seq for event in events], list(range(1, len(events) + 1)))
            self.assertIn('tool_end', [event.name for event in events])
            payload = report_payload({'task_id': 't', 'run_id': 'r'}, result)
            ExecutionReportWire.model_validate(payload)
            second = await runtime.run('第二轮问题', history=result.messages, stop=asyncio.Event(),
                                       on_event=lambda _: None, channel=RunChannel())
            self.assertNotEqual(result.output['report_path'], second.output['report_path'])
            retained, _ = read_session_file('anon:demo', 'ses_' + 'a' * 32, result.output['report_path'])
            self.assertEqual(retained, content)

    async def test_failure_timeout_and_stop(self):
        with patch('agent_app.demo_worker.asyncio.sleep', new_callable=AsyncMock):
            for prompt, expected in [('[失败] 测试', 'failed'), ('[超时] 测试', 'timeout'), ('停止', 'stopped')]:
                stop = asyncio.Event()
                if expected == 'stopped':
                    stop.set()
                runtime = DemoRuntime(owner='anon:demo', session_id='ses_' + 'b' * 32, mode='fast', model='demo/m1')
                result = await runtime.run(prompt, history=[], stop=stop, on_event=lambda _: None, channel=RunChannel())
                self.assertEqual(result.status, expected)

    async def test_demo_environment_refuses_real_worker_and_non_demo_model(self):
        with patch.dict('os.environ', {'AGENT_DEMO_MODE': '1'}):
            with self.assertRaisesRegex(RuntimeError, '禁止启动真实模型'):
                await run_worker_forever()
        with self.assertRaises(ValueError):
            DemoRuntime(owner='anon:demo', session_id='s', mode='fast', model='real/model')

    async def test_demo_config_is_explicit_and_wire_compatible(self):
        with patch.dict('os.environ', {'AGENT_DEMO_MODE': '1', 'AGENT_SERVICE_TOKEN': 'demo-token'}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test',
                                         headers={'Authorization': 'Bearer demo-token'}) as client:
                response = await client.get('/internal/v1/config')
                config = AgentConfigWire.model_validate(response.json())
                self.assertEqual(config.default_model, 'demo/m1')
                self.assertIn('Mock', config.models[0]['label'])

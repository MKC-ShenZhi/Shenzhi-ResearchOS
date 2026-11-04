"""Execute the shipped HTTP trigger with mocked transport, never a real URL."""
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta
import urllib.error
import yaml
from app.services.conferences_sync import ConferenceSync
from tests.test_conferences_sync import NOW, SHA

WORKFLOW = Path(__file__).parents[3] / '.github/workflows/conference-sync.yml'

class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.load(WORKFLOW.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
        self.script = self.workflow['jobs']['trigger']['steps'][0]['run']
        self.env = {'CONFERENCE_SYNC_URL': 'https://backend.example/api/v1/internal/conference-sync', 'CONFERENCE_CRON_SECRET': 'test-only-secret-32-characters'}

    def invoke(self, response=None, error=None, env=None):
        response = response or {'code': 0, 'data': {'status': 'updated'}}
        stream = MagicMock()
        stream.status = 200
        stream.read.return_value = json.dumps(response).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = stream
        opener.open.side_effect = error
        output = io.StringIO()
        with patch.dict(os.environ, self.env if env is None else env), patch('urllib.request.build_opener', return_value=opener), contextlib.redirect_stdout(output):
            try:
                exec(compile(self.script, str(WORKFLOW), 'exec'), {})
                code = 0
            except SystemExit as caught:
                code = caught.code
        return code, output.getvalue(), opener

    def test_hourly_http_only_without_write_permissions(self):
        self.assertEqual(self.workflow['on']['schedule'][0]['cron'], '17 * * * *')
        self.assertEqual(self.workflow['permissions'], {})
        self.assertEqual(len(self.workflow['jobs']['trigger']['steps']), 1)
        self.assertEqual(self.workflow['concurrency']['cancel-in-progress'], 'false')

    def test_success_and_safe_skip_acknowledged_with_authenticated_request(self):
        for status in ('updated', 'unchanged', 'locked', 'not-due', 'retry-delayed'):
            code, output, opener = self.invoke({'code': 0, 'data': {'status': status}})
            self.assertEqual(code, 0)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + self.env['CONFERENCE_CRON_SECRET'])
            self.assertNotIn(self.env['CONFERENCE_CRON_SECRET'], output)
            self.assertEqual(opener.open.call_args.kwargs['timeout'], 260)

    def test_failures_mark_workflow_failed_and_hide_secrets(self):
        for error in (TimeoutError('private endpoint and secret'), urllib.error.HTTPError(self.env['CONFERENCE_SYNC_URL'], 503, 'sensitive', {}, None)):
            code, output, _ = self.invoke(error=error)
            self.assertEqual(code, 1)
            self.assertNotIn('private endpoint', output)
            self.assertNotIn(self.env['CONFERENCE_SYNC_URL'], output)
            self.assertNotIn(self.env['CONFERENCE_CRON_SECRET'], output)
        code, _, _ = self.invoke({'code': 0, 'data': {'status': 'unexpected'}})
        self.assertEqual(code, 1)

    def test_bad_configuration_never_makes_request(self):
        for env in ({**self.env, 'CONFERENCE_SYNC_URL': 'http://backend.example/api/v1/internal/conference-sync'}, {**self.env, 'CONFERENCE_SYNC_URL': self.env['CONFERENCE_SYNC_URL'] + '?token=oops'}, {**self.env, 'CONFERENCE_CRON_SECRET': ''}):
            code, _, opener = self.invoke(env=env)
            self.assertEqual(code, 1)
            opener.open.assert_not_called()

class AutomaticRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_hourly_retry_survives_new_service_instance(self):
        state = SimpleNamespace(snapshot_id='previous', upstream_sha=SHA, checked_at=NOW-timedelta(days=2), attempted_at=NOW-timedelta(days=2))
        async def attempted(at):
            state.attempted_at = at
        async def checked(at):
            state.checked_at = at
        store = SimpleNamespace(state=AsyncMock(return_value=state), attempt=AsyncMock(side_effect=attempted), checked=AsyncMock(side_effect=checked), save=AsyncMock())
        client = SimpleNamespace(latest=AsyncMock(side_effect=[TimeoutError(), (SHA, '2026-11-03')]), download=AsyncMock())
        with self.assertRaises(TimeoutError):
            await ConferenceSync(store, client).sync(now=NOW)
        result = await ConferenceSync(store, client).sync(now=NOW+timedelta(minutes=59))
        self.assertEqual(result['status'], 'retry-delayed')
        self.assertEqual(client.latest.await_count, 1)
        result = await ConferenceSync(store, client).sync(now=NOW+timedelta(hours=1))
        self.assertEqual(result['status'], 'unchanged')
        result = await ConferenceSync(store, client).sync(now=NOW+timedelta(hours=2))
        self.assertEqual(result['status'], 'not-due')
        self.assertEqual(client.latest.await_count, 2)
        client.download.assert_not_awaited()
        store.save.assert_not_awaited()

    async def test_hourly_checks_do_not_download_or_poll_github_before_due(self):
        state = SimpleNamespace(snapshot_id='previous', upstream_sha=SHA, checked_at=NOW, attempted_at=NOW)
        store = SimpleNamespace(state=AsyncMock(return_value=state), attempt=AsyncMock(), checked=AsyncMock())
        client = SimpleNamespace(latest=AsyncMock(return_value=(SHA, '2026-11-03')), download=AsyncMock())
        for hour in range(22):
            result = await ConferenceSync(store, client).sync(now=NOW+timedelta(hours=hour))
            self.assertEqual(result['status'], 'not-due')
        client.latest.assert_not_awaited()
        result = await ConferenceSync(store, client).sync(now=NOW+timedelta(hours=22))
        self.assertEqual(result['status'], 'unchanged')
        client.latest.assert_awaited_once()
        client.download.assert_not_awaited()

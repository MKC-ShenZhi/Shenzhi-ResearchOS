import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.services import anonymous_cleanup


class AnonymousCleanupTests(unittest.IsolatedAsyncioTestCase):
    def test_ttl_defaults_and_rejects_invalid_values(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(anonymous_cleanup.anonymous_ttl_seconds(), 604800)
        for value in ('0', '-1', 'not-a-number'):
            with self.subTest(value=value), patch.dict('os.environ', {
                'CHAT_ANONYMOUS_TTL_SECONDS': value,
            }, clear=True):
                with self.assertRaises(ValueError):
                    anonymous_cleanup.anonymous_ttl_seconds()

    async def test_cleanup_requires_durable_repository(self):
        with patch.object(anonymous_cleanup.repository, 'is_durable', False):
            with self.assertRaisesRegex(RuntimeError, 'CHAT_DATABASE_URL'):
                await anonymous_cleanup.purge_expired_anonymous_sessions()

    async def test_cleanup_uses_configured_ttl_and_returns_deleted_count(self):
        purge = AsyncMock(return_value=3)
        now = datetime(2026, 9, 5, tzinfo=timezone.utc)
        with patch.object(anonymous_cleanup.repository, 'is_durable', True), \
             patch.object(anonymous_cleanup.repository, 'purge_expired_anonymous_sessions', purge), \
             patch.dict('os.environ', {'CHAT_ANONYMOUS_TTL_SECONDS': '60'}, clear=True):
            self.assertEqual(await anonymous_cleanup.purge_expired_anonymous_sessions(now), 3)
        self.assertEqual(purge.await_args.args[0].isoformat(), '2026-09-04T23:59:00+00:00')

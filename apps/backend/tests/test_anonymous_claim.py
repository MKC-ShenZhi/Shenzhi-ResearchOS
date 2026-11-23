"""Backend coordinates ownership changes through the Agent Gateway."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.identity import anonymous_claim


SOURCE_OWNER = 'anon:00000000-0000-4000-8000-000000000001'
TARGET_OWNER = 'user:claimed'


class FakeSessionRepository:
    async def claimable_session_ids(self, owner):
        assert owner == SOURCE_OWNER
        return ['session-1']

    async def claim_anonymous_sessions(self, source, target, *, session_ids):
        assert (source, target, session_ids) == (SOURCE_OWNER, TARGET_OWNER, ['session-1'])
        return {'moved_count': 1, 'skipped_running_count': 0,
                'moved_session_ids': ['session-1'], 'durable': True}


class FakeGateway:
    def __init__(self):
        self.calls = []
        self.prepare_error = None
        self.commit_error = None

    async def prepare_workspace_claim(self, source, target, session_ids):
        self.calls.append(('prepare', source, target, session_ids))
        if self.prepare_error:
            raise self.prepare_error
        return {'prepared_session_ids': session_ids}

    async def commit_workspace_claim(self, source, target, session_ids):
        self.calls.append(('commit', source, target, session_ids))
        if self.commit_error:
            raise self.commit_error


class FakeUploads:
    def __init__(self):
        self.claims = []

    async def claim_owner(self, source, target):
        self.claims.append((source, target))


class AnonymousClaimTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = FakeGateway()
        self.uploads = FakeUploads()
        self.patches = [
            patch.object(anonymous_claim, 'agent_session_repository', FakeSessionRepository()),
            patch.object(anonymous_claim, 'agent_gateway', self.gateway),
            patch.object(anonymous_claim, 'agent_upload_store', self.uploads),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    async def test_gateway_prepares_before_backend_ownership_commit_then_cleans_source(self):
        result = await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)
        self.assertEqual(result, {'moved_count': 1, 'skipped_streaming_count': 0, 'durable': True})
        self.assertEqual([call[0] for call in self.gateway.calls], ['prepare', 'commit'])
        self.assertEqual(self.uploads.claims, [(SOURCE_OWNER, TARGET_OWNER)])

    async def test_prepare_failure_does_not_change_backend_ownership(self):
        self.gateway.prepare_error = RuntimeError('Agent unavailable')
        with self.assertRaisesRegex(RuntimeError, 'Agent unavailable'):
            await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)
        self.assertEqual([call[0] for call in self.gateway.calls], ['prepare'])
        self.assertEqual(self.uploads.claims, [])

    async def test_commit_failure_does_not_reverse_committed_backend_claim(self):
        self.gateway.commit_error = RuntimeError('cleanup unavailable')
        result = await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)
        self.assertEqual(result['moved_count'], 1)
        self.assertEqual([call[0] for call in self.gateway.calls], ['prepare', 'commit'])
        self.assertEqual(self.uploads.claims, [(SOURCE_OWNER, TARGET_OWNER)])


if __name__ == '__main__':
    unittest.main()

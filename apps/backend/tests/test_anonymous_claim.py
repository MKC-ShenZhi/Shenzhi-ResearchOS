"""Anonymous ownership migration keeps Agent DB and workspace state aligned."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.agent import workspace as agent_workspace
from app.services.agent_sessions.repository import MemoryAgentSessionRepository
from app.services.identity import anonymous_claim


SOURCE_OWNER = 'anon:00000000-0000-4000-8000-000000000001'
TARGET_OWNER = 'user:claimed'


class FakeChatRepository:
    is_durable = True

    async def claim_anonymous_sessions(self, source_owner: str, target_owner: str) -> dict:
        return {'moved_count': 0, 'skipped_streaming_count': 0, 'durable': True}


class FakeAgentRepository:
    is_durable = True

    def __init__(self, session_ids: list[str]):
        self.sessions = {
            session_id: {'owner': SOURCE_OWNER, 'running': False}
            for session_id in session_ids
        }
        self.fail_claim = False
        self.mark_running_before_claim: str | None = None
        self.claim_calls = 0

    async def claimable_session_ids(self, source_owner: str) -> list[str]:
        return [
            session_id
            for session_id, state in self.sessions.items()
            if state['owner'] == source_owner and not state['running']
        ]

    async def claim_anonymous_sessions(
        self,
        source_owner: str,
        target_owner: str,
        *,
        session_ids: list[str],
    ) -> dict:
        self.claim_calls += 1
        if self.fail_claim:
            raise RuntimeError('database unavailable')
        if self.mark_running_before_claim:
            self.sessions[self.mark_running_before_claim]['running'] = True
        moved_ids = []
        for session_id in session_ids:
            state = self.sessions.get(session_id)
            if state and state['owner'] == source_owner and not state['running']:
                state['owner'] = target_owner
                moved_ids.append(session_id)
        skipped = sum(
            state['owner'] == source_owner and state['running']
            for state in self.sessions.values()
        )
        return {
            'moved_count': len(moved_ids),
            'skipped_running_count': skipped,
            'moved_session_ids': moved_ids,
            'durable': True,
        }


class AnonymousClaimTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_patch = patch.object(
            agent_workspace, 'WORKSPACE_ROOT', Path(self.temp_dir.name)
        )
        self.workspace_patch.start()
        self.chat_patch = patch.object(
            anonymous_claim, 'chat_repository', FakeChatRepository()
        )
        self.chat_patch.start()
        self.upload_patch = patch.object(
            agent_workspace, 'migrate_owner_workspaces', return_value=0
        )
        self.upload_patch.start()

    def tearDown(self):
        self.upload_patch.stop()
        self.chat_patch.stop()
        self.workspace_patch.stop()
        self.temp_dir.cleanup()

    def use_agent_repository(self, session_ids: list[str]) -> FakeAgentRepository:
        repository = FakeAgentRepository(session_ids)
        self.agent_patch = patch.object(
            anonymous_claim, 'agent_session_repository', repository
        )
        self.agent_patch.start()
        self.addCleanup(self.agent_patch.stop)
        return repository

    @staticmethod
    def write_source(session_id: str, content: str = 'source report') -> Path:
        source = agent_workspace._owner_dir(SOURCE_OWNER) / session_id
        source.mkdir(parents=True, exist_ok=True)
        (source / 'report.md').write_text(content, encoding='utf-8')
        return source

    @staticmethod
    def target(session_id: str) -> Path:
        return agent_workspace._owner_dir(TARGET_OWNER) / session_id

    async def test_copy_failure_keeps_db_owner_and_source_for_retry(self):
        repository = self.use_agent_repository(['ses_copy_failure'])
        source = self.write_source('ses_copy_failure')
        with patch.object(
            agent_workspace,
            'copy_session_workspace',
            side_effect=OSError('copy failed'),
        ):
            with self.assertRaises(OSError):
                await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)

        self.assertEqual(repository.claim_calls, 0)
        self.assertEqual(repository.sessions['ses_copy_failure']['owner'], SOURCE_OWNER)
        self.assertTrue((source / 'report.md').exists())

    async def test_db_failure_keeps_source_and_allows_extra_target_copy(self):
        repository = self.use_agent_repository(['ses_db_failure'])
        repository.fail_claim = True
        source = self.write_source('ses_db_failure')

        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)

        self.assertEqual(repository.sessions['ses_db_failure']['owner'], SOURCE_OWNER)
        self.assertTrue((source / 'report.md').exists())
        self.assertEqual(
            (self.target('ses_db_failure') / 'report.md').read_text(encoding='utf-8'),
            'source report',
        )

    async def test_success_copies_target_commits_owner_and_cleans_source(self):
        repository = self.use_agent_repository(['ses_success'])
        source = self.write_source('ses_success')

        result = await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)

        self.assertEqual(result['moved_count'], 1)
        self.assertEqual(repository.sessions['ses_success']['owner'], TARGET_OWNER)
        self.assertFalse(source.exists())
        self.assertEqual(
            (self.target('ses_success') / 'report.md').read_text(encoding='utf-8'),
            'source report',
        )

    async def test_cleanup_failures_do_not_fail_a_committed_claim(self):
        repository = self.use_agent_repository(['ses_cleanup_failure'])
        source = self.write_source('ses_cleanup_failure')
        with (
            patch.object(
                agent_workspace,
                'cleanup_session_workspace',
                side_effect=OSError('cleanup failed'),
            ),
            patch.object(
                agent_workspace,
                'migrate_owner_workspaces',
                side_effect=OSError('uploaded cleanup failed'),
            ),
        ):
            result = await anonymous_claim.claim_anonymous_sessions(
                SOURCE_OWNER, TARGET_OWNER
            )

        self.assertEqual(result['moved_count'], 1)
        self.assertEqual(repository.sessions['ses_cleanup_failure']['owner'], TARGET_OWNER)
        self.assertTrue(source.exists())
        self.assertTrue((self.target('ses_cleanup_failure') / 'report.md').exists())

    async def test_session_that_starts_running_after_prepare_is_not_moved_or_cleaned(self):
        repository = self.use_agent_repository(['ses_race'])
        repository.mark_running_before_claim = 'ses_race'
        source = self.write_source('ses_race')

        result = await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)

        self.assertEqual(result['moved_count'], 0)
        self.assertEqual(result['skipped_streaming_count'], 1)
        self.assertEqual(repository.sessions['ses_race']['owner'], SOURCE_OWNER)
        self.assertTrue((source / 'report.md').exists())
        self.assertTrue((self.target('ses_race') / 'report.md').exists())

    async def test_retry_merges_partial_target_without_losing_or_duplicating_files(self):
        repository = self.use_agent_repository(['ses_retry'])
        source = self.write_source('ses_retry', 'first copy')
        repository.fail_claim = True
        with self.assertRaises(RuntimeError):
            await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)

        target = self.target('ses_retry')
        (target / 'target-only.txt').write_text('keep me', encoding='utf-8')
        (source / 'report.md').write_text('retry copy', encoding='utf-8')
        (source / 'image.png').write_bytes(b'image')
        repository.fail_claim = False

        result = await anonymous_claim.claim_anonymous_sessions(SOURCE_OWNER, TARGET_OWNER)

        self.assertEqual(result['moved_count'], 1)
        self.assertEqual(len(repository.sessions), 1)
        self.assertEqual(repository.sessions['ses_retry']['owner'], TARGET_OWNER)
        self.assertFalse(source.exists())
        self.assertEqual((target / 'report.md').read_text(encoding='utf-8'), 'retry copy')
        self.assertEqual((target / 'image.png').read_bytes(), b'image')
        self.assertEqual(
            (target / 'target-only.txt').read_text(encoding='utf-8'), 'keep me'
        )

    async def test_memory_repository_keeps_non_durable_noop_contract(self):
        repository = MemoryAgentSessionRepository()
        self.assertEqual(await repository.claimable_session_ids(SOURCE_OWNER), [])
        result = await repository.claim_anonymous_sessions(
            SOURCE_OWNER, TARGET_OWNER, session_ids=[]
        )
        self.assertEqual(result, {
            'moved_count': 0,
            'skipped_running_count': 0,
            'moved_session_ids': [],
            'durable': False,
        })


if __name__ == '__main__':
    unittest.main()

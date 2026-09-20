"""Process-local cleanup guarantees used by account deletion."""

import asyncio
import unittest

from app.services.chat.repository import MemorySessionRepository


class AccountDeletionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_cleanup_cancels_tasks_and_preserves_other_owner(self):
        repository = MemorySessionRepository()
        target = await repository.create('user:target', 'target', {})
        target_message = await repository.add_message(target, 'question', {})
        other = await repository.create('user:other', 'other', {})
        other_message = await repository.add_message(other, 'question', {})

        started = asyncio.Event()

        async def active_generation():
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(active_generation())
        target_message.task = task
        await started.wait()
        target_upload = repository.save_upload('user:target', 'target.txt', {'content': 'private'})
        other_upload = repository.save_upload('user:other', 'other.txt', {'content': 'keep'})

        await repository.purge_owner_runtime('user:target')

        self.assertTrue(task.cancelled())
        self.assertNotIn(target.id, repository.sessions)
        self.assertNotIn(target_message.id, repository.messages)
        self.assertNotIn(target_upload['file_id'], repository.uploads)
        self.assertIn(other.id, repository.sessions)
        self.assertIn(other_message.id, repository.messages)
        self.assertIn(other_upload['file_id'], repository.uploads)

        await repository.purge_owner_runtime('user:target')


if __name__ == '__main__':
    unittest.main()

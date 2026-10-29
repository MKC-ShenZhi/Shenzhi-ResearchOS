"""Read badges must query the signed-in user's paper history only."""

import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from app.services.library.reading_history import ReadingHistoryService


class CaptureSession:
    def __init__(self):
        self.parameters = {}

    async def scalars(self, statement):
        self.parameters = statement.compile().params
        return iter(['paper:b'])

    async def execute(self, statement):
        self.parameters = statement.compile().params
        self.statement = statement
        return self

    async def scalar(self, statement):
        # mark_read uses RETURNING to emit the read event only on the first
        # completion; None models "already read", so no event row is added.
        self.parameters = statement.compile().params
        self.statement = statement
        return None

    def all(self):
        return [('paper:a', None), ('paper:b', '2026-10-14')]


class PaperReadStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_upserts_without_replacing_last_visit_time(self):
        session = CaptureSession()

        @asynccontextmanager
        async def fake_scope():
            yield session

        with patch('app.services.library.reading_history.session_scope', fake_scope):
            await ReadingHistoryService().mark_read('user-a', 'paper:a')

        sql = str(session.statement.compile())
        self.assertIn('ON CONFLICT', sql)
        self.assertIn('read_at', sql)
        self.assertNotIn('last_viewed_at =', sql)
        # A repeated completion keeps the first read_at instead of moving it.
        self.assertIn('WHERE reading_history.read_at IS NULL', sql)
        self.assertIn('user-a', session.parameters.values())
        self.assertIn('paper:a', session.parameters.values())

    async def test_batch_is_filtered_by_user_and_requested_papers(self):
        session = CaptureSession()

        @asynccontextmanager
        async def fake_scope():
            yield session

        with patch('app.services.library.reading_history.session_scope', fake_scope):
            result = await ReadingHistoryService().paper_status_ids(
                'user-a', ['paper:a', 'paper:b'],
            )

        self.assertEqual(result, (['paper:b'], ['paper:a']))
        self.assertIn('user-a', session.parameters.values())
        self.assertIn(['paper:a', 'paper:b'], session.parameters.values())


if __name__ == '__main__':
    unittest.main()

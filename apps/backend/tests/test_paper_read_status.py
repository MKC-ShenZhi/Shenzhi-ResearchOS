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


class PaperReadStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_is_filtered_by_user_and_requested_papers(self):
        session = CaptureSession()

        @asynccontextmanager
        async def fake_scope():
            yield session

        with patch('app.services.library.reading_history.session_scope', fake_scope):
            result = await ReadingHistoryService().read_paper_ids(
                'user-a', ['paper:a', 'paper:b'],
            )

        self.assertEqual(result, ['paper:b'])
        self.assertIn('user-a', session.parameters.values())
        self.assertIn(['paper:a', 'paper:b'], session.parameters.values())


if __name__ == '__main__':
    unittest.main()

import unittest
from app.services.agent_sessions.timeline import TimelineCapture


class CloseoutTests(unittest.TestCase):
    def test_retry_turn_numbers_do_not_join_reasoning(self):
        capture = TimelineCapture([])
        for _ in range(3):
            capture.event('run_start', {'run_id': str(_)})
            capture.event('delta', {'turn': 1, 'reasoning': '思考'})
            capture.event('delta', {'turn': 1, 'reasoning': '中'})
        self.assertEqual(capture.process, [{'kind': 'reasoning', 'text': '思考中'}] * 3)

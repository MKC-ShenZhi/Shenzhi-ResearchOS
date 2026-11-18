import copy
import unittest

from app.services.agent_sessions.timeline import TimelineCapture


class TimelineRunToolTests(unittest.TestCase):
    def test_retry_runs_with_same_tool_id_only_complete_current_tool(self):
        capture = TimelineCapture([])
        historical = []
        for run in range(3):
            capture.event('run_start', {'run_id': str(run)})
            capture.event('delta', {'turn': 1, 'reasoning': '思考'})
            capture.event('delta', {'turn': 2, 'reasoning': '下一轮'})
            capture.event('tool_call', {
                'tool_call_id': 'shared', 'name': 'paper_search', 'arguments': '{}',
            })
            capture.event('tool_end', {
                'tool_call_id': 'shared', 'is_error': run == 1,
                'duration_ms': run + 1, 'summary': f'Run {run}',
            })
            self.assertEqual(capture.process[:len(historical)], historical)
            self.assertEqual(capture.process[-1], {'kind': 'tool', 'tool': {
                'toolCallId': 'shared', 'name': 'paper_search', 'arguments': '{}',
                'done': True, 'isError': run == 1, 'durationMs': run + 1,
                'summary': f'Run {run}',
            }})
            historical = copy.deepcopy(capture.process)

    def test_unmatched_tool_end_in_new_run_leaves_history_untouched(self):
        capture = TimelineCapture([])
        capture.event('run_start', {'run_id': 'first'})
        capture.event('tool_call', {'tool_call_id': 'shared', 'name': 'paper_search'})
        historical = copy.deepcopy(capture.process)
        capture.event('run_start', {'run_id': 'retry'})
        capture.event('delta', {'turn': 1, 'reasoning': '新 Run'})
        capture.event('tool_end', {
            'tool_call_id': 'shared', 'is_error': True, 'duration_ms': 99, 'summary': 'unmatched',
        })
        self.assertEqual(capture.process[:len(historical)], historical)

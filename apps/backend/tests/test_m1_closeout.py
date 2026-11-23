import importlib.util
from pathlib import Path
import tempfile
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

    def test_launcher_scrubs_names_without_parsing_values(self):
        path = Path(__file__).resolve().parents[3] / 'scripts/agent_m1_demo.py'
        spec = importlib.util.spec_from_file_location('m1_demo_closeout', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / '.env.local'
            source.write_text('export KEY="private"\nBROKEN="unterminated\nOTHER=value\n', encoding='utf-8')
            with self.assertNoLogs('dotenv.main', level='WARNING'):
                self.assertEqual(module.environment_keys(source), ['KEY', 'BROKEN', 'OTHER'])

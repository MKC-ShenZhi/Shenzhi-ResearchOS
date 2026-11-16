"""Offline verification of the evidence-gathering script; never calls AutoDL."""
import json
import unittest
from unittest.mock import patch

import httpx

from scripts.autodl_probe import Probe, redact, run


def events(*deltas):
    return ''.join('data: ' + json.dumps({'choices': [{'delta': delta, 'finish_reason': finish}]})
                   + '\n\n' for delta, finish in deltas) + 'data: [DONE]\n\n'


class AutoDLProbeTests(unittest.TestCase):
    def test_fragmented_two_turn_tools_twice_without_reasoning_in_history(self):
        seen = []

        def handler(request):
            payload = json.loads(request.content)
            seen.append(payload)
            self.assertEqual(payload['enable_thinking'], False)
            if len(payload['messages']) == 1:
                return httpx.Response(200, text=events(
                    ({'reasoning_content': 'private thought', 'tool_calls': [{
                        'index': 0, 'id': 'call1', 'function': {'name': 'echo', 'arguments': '{"text":'}}]}, None),
                    ({'tool_calls': [{'index': 0, 'function': {'arguments': '"ok"}'}}]}, 'tool_calls')))
            assistant = payload['messages'][1]
            self.assertNotIn('reasoning_content', assistant)
            self.assertNotIn('reasoning', assistant)
            self.assertEqual(payload['messages'][2]['tool_call_id'], 'call1')
            self.assertEqual(json.loads(payload['messages'][2]['content']), 'ok')
            return httpx.Response(200, text=events(({'content': 'OK'}, 'stop')))

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = Probe(client, 'https://probe.example/v1', 'private-key').tools('Exact-ID', {'enable_thinking': False})
        self.assertTrue(result['pass'])
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(item['round1']['tool_call_fragments'] == 2 for item in result['runs']))

    def test_one_success_does_not_claim_tools_supported(self):
        with httpx.Client() as client:
            probe = Probe(client, 'https://probe.example', 'private-key')
            with patch.object(probe, 'tool_run', side_effect=[{'pass': True}, {'pass': False}]):
                self.assertFalse(probe.tools('m', {})['pass'])

    def test_first_chunk_closes_without_consuming_generation(self):
        class Stream(httpx.SyncByteStream):
            closed = False

            def __iter__(self):
                yield b'data: {"choices":[]}\n\n'
                raise AssertionError('must close after first chunk')

            def close(self):
                self.closed = True

        stream = Stream()
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))) as client:
            result = Probe(client, 'https://probe.example', 'private-key').stream('m', first_chunk=True)
        self.assertTrue(result['first_chunk_received'])
        self.assertTrue(stream.closed)

    def test_t0_missing_model_stops_before_completion_calls(self):
        def handler(request):
            self.assertEqual(request.method, 'GET')
            return httpx.Response(200, json={'data': [{'id': 'OtherModel'}]})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = run(Probe(client, 'https://probe.example', 'private-key'), ['OtherModel'])
        self.assertIn('DeepSeek V4.1', result['stop_reason'])
        self.assertEqual(result['models'], {})

    def test_errors_redact_key_and_prefix_before_truncation(self):
        secret = 'probe-private-credential-never-real'
        body = f'Authorization: Bearer {secret}; prefix={secret[:8]}'
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(402, text=body))) as client:
            probe = Probe(client, 'https://probe.example', secret)
            result = probe.error('m')
        self.assertEqual(result['status'], 402)
        self.assertNotIn(secret[:8], json.dumps(result))
        self.assertNotIn(secret[:8], redact(body, secret))

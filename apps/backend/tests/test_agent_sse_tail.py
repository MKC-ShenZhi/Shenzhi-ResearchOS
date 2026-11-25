"""Terminal/event races across the three product streams, without remote services."""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from app.api import agent as api
from app.services.agent_sessions import live as live_runs, service
from app.services.agent_sessions.repository import MemoryAgentSessionRepository


class TailGateway:
    """Commit the tail and report immediately after the first event snapshot."""

    def __init__(self, *, race=False, retry=False):
        self.terminal = not race
        self.retry = retry
        self.stored = [self.event(1)] if race else [self.event(1), self.event(2)]
        self.reads = []

    @staticmethod
    def event(seq):
        return {'seq': seq, 'name': 'delta', 'data': {'turn': 1, 'text': str(seq)}}

    async def submit(self, payload):
        return {'task_id': 'task-1', 'current_run_id': 'run-1'}

    async def run(self, run_id, owner):
        self.reads.append(('run', run_id))
        if run_id == 'run-1' and not self.terminal:
            return {'report': None}
        return {'report': {
            'status': 'failed' if self.retry and run_id == 'run-1' else 'completed',
            'result': {'final_text': 'complete', 'stop_reason': 'stop', 'messages': []},
        }}

    async def events(self, run_id, owner, after_seq):
        self.reads.append(('events', run_id, after_seq))
        stored = self.stored if run_id == 'run-1' else [self.event(3)]
        snapshot = [event for event in stored if event['seq'] > after_seq]
        if run_id == 'run-1' and not self.terminal:
            # The caller's first snapshot cannot see these committed writes.
            self.stored.append(self.event(2))
            self.terminal = True
        return snapshot

    async def task(self, task_id, owner):
        return {'current_run_id': 'run-2' if self.retry and self.terminal else 'run-1'}

    async def task_runs(self, task_id, owner):
        return ['run-1', 'run-2'] if self.retry and self.terminal else ['run-1']

    async def usage(self, task_id, owner):
        return {}


def decode(chunk):
    if isinstance(chunk, bytes):
        chunk = chunk.decode('utf-8')
    fields = dict(line.split(': ', 1) for line in chunk.splitlines() if ': ' in line)
    if 'event' not in fields:
        return None
    return (int(fields['id']) if 'id' in fields else None,
            fields['event'], json.loads(fields['data']))


class AgentSseTailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.dict('os.environ', {'CHAT_DATABASE_URL': ''}))
        self.repo = MemoryAgentSessionRepository()
        self.enterContext(patch.object(service, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(api, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(live_runs, '_live', {}))
        self.owner = 'anon:sse-tail'

    def gateway(self, **options):
        gateway = TailGateway(**options)
        self._gateway = gateway
        self.enterContext(patch('app.services.agent_gateway.v2.AgentGatewayV2', return_value=gateway))
        return gateway

    async def stream(self, mode):
        if mode == 'stateless':
            return api._agent_task_stream(self.owner, {
                'task_id': 'task-1', 'current_run_id': 'run-1',
            }, [])
        session = await self.repo.create(self.owner, 'tail', {})
        self.session_id = session.id
        if mode == 'initial':
            live = await service.start_session_run(
                owner=self.owner, session_id=session.id, prompt='tail', model=None,
                mode='fast', attachments=[], workspace_id=None, skills=[],
                gateway=self._gateway,
            )
        else:
            await self.repo.start_turn(session.id, self.owner, 'tail', {
                '_agent_protocol': 2, 'agent_task_id': 'task-1', 'agent_run_id': 'run-1',
            }, [])
            live = await service.resume_session_run(session.id, self.owner)
        self.live = live
        return api.session_run_stream(live).body_iterator

    async def drain(self, stream):
        return [event async for chunk in stream if (event := decode(chunk)) is not None]

    def assert_complete(self, events, expected=('1', '2')):
        self.assertEqual([data['text'] for _, name, data in events if name == 'delta'],
                         list(expected))
        self.assertEqual(events[-1][1], 'result')
        self.assertEqual(events[-1][2]['status'], 'done')
        self.assertEqual(sum(name == 'result' for _, name, _ in events), 1)

    async def check_tail(self, mode, *, race):
        gateway = self.gateway(race=race)
        events = await self.drain(await self.stream(mode))
        self.assert_complete(events)
        if race:
            self.assertEqual([read[2] for read in gateway.reads if read[0] == 'events'], [0, 1])
        if mode != 'stateless':
            session = await self.repo.get(self.session_id, self.owner)
            self.assertEqual(session.turns[-1].status, 'done')
            texts = ''.join(item.get('text', '') for item in session.turns[-1].process
                            if item['kind'] == 'text')
            self.assertEqual(texts, '12')

    async def test_stateless_normal_end(self):
        await self.check_tail('stateless', race=False)

    async def test_stateless_terminal_tail_race(self):
        await self.check_tail('stateless', race=True)

    async def test_initial_projection_normal_end(self):
        await self.check_tail('initial', race=False)

    async def test_initial_projection_terminal_tail_race(self):
        await self.check_tail('initial', race=True)

    async def test_recovery_projection_normal_end(self):
        await self.check_tail('recovery', race=False)

    async def test_recovery_projection_terminal_tail_race(self):
        await self.check_tail('recovery', race=True)

    async def check_reconnect(self, *, discard_cache, interrupt_projection=False):
        self.gateway(race=True)
        stream = await self.stream('initial')
        self.assertEqual(decode(await anext(stream))[1], 'run_start')
        first = decode(await anext(stream))
        self.assertEqual(first[1:], ('delta', {'turn': 1, 'text': '1'}))
        await stream.aclose()
        if discard_cache:
            if interrupt_projection:
                self.assertFalse(self.live.task.done())
                self.live.task.cancel()
                await asyncio.gather(self.live.task, return_exceptions=True)
            else:
                await self.live.task
            live_runs._live.clear()
        response = await api.attach_agent_session_run(
            self.session_id, after=first[0] + 1, owner=self.owner,
        )
        remaining = await self.drain(response.body_iterator)
        self.assert_complete(remaining, expected=('2',))
        combined = [first, *remaining]
        self.assertEqual([event[0] for event in combined], [1, 2, 3])

    async def test_reconnect_to_live_projection_has_no_duplicates_or_gaps(self):
        await self.check_reconnect(discard_cache=False)

    async def test_reconnect_rebuilds_projection_without_duplicates_or_gaps(self):
        await self.check_reconnect(discard_cache=True)

    async def test_reconnect_recovers_interrupted_active_projection(self):
        await self.check_reconnect(discard_cache=True, interrupt_projection=True)

    async def test_retry_switch_drains_previous_run_tail_in_all_streams(self):
        for mode in ('stateless', 'initial', 'recovery'):
            with self.subTest(mode=mode):
                gateway = self.gateway(race=True, retry=True)
                events = await self.drain(await self.stream(mode))
                self.assert_complete(events, expected=('1', '2', '3'))
                self.assertIn(('events', 'run-1', 1), gateway.reads)


if __name__ == '__main__':
    unittest.main()

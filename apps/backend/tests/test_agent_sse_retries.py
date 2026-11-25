"""Stable Session SSE offsets across complete retry history and cache loss."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.api import agent as api
from app.core.errors import BusinessError
from app.services.agent_sessions import live as live_runs, service
from app.services.agent_sessions.repository import MemoryAgentSessionRepository
from tests.test_agent_sse_tail import decode


class RetryGateway:
    def __init__(self, count=3, *, active=False, tail=False, final_status='completed'):
        self.ids = [f'r{index}' for index in range(1, count + 1)]
        self.ready = asyncio.Event()
        if not active:
            self.ready.set()
        self.tail = tail
        self.final_status = final_status
        self.reads = []

    async def submit(self, payload):
        # Idempotent submission can already point to a later retry.
        return {'task_id': 't1', 'current_run_id': self.ids[-1]}

    async def task_runs(self, task_id, owner):
        self.reads.append(('runs', owner))
        return self.ids[:] if self.ready.is_set() else self.ids[:1]

    async def usage(self, task_id, owner):
        return {}

    async def run(self, run_id, owner):
        self.reads.append(('run', run_id))
        if not self.ready.is_set():
            return {'report': None}
        status = (self.final_status if run_id == self.ids[-1]
                  else 'failed' if run_id == 'r1' else 'timed_out')
        return {'report': {
            'status': status, 'result': {'final_text': 'final', 'stop_reason': status},
        }}

    async def events(self, run_id, owner, after_seq):
        self.reads.append(('events', run_id, after_seq))
        # Internal seq may contain gaps; SSE IDs are contiguous product offsets.
        events = [{'seq': 3, 'name': 'delta', 'data': {'turn': 1, 'text': run_id}}]
        if self.tail and run_id == 'r1' and self.ready.is_set():
            events.append({'seq': 8, 'name': 'delta', 'data': {'turn': 1, 'text': 'tail'}})
        return [event for event in events if event['seq'] > after_seq]


class SessionRetrySseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.dict('os.environ', {'CHAT_DATABASE_URL': ''}))
        self.repo = MemoryAgentSessionRepository()
        self.enterContext(patch.object(service, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(api, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(live_runs, '_live', {}))
        self.owner = 'anon:retries'

    async def start(self, gateway, *, recover=False):
        self.enterContext(patch('app.services.agent_gateway.gateway.AgentGateway', return_value=gateway))
        session = await self.repo.create(self.owner, 'retry', {})
        if recover:
            await self.repo.start_turn(session.id, self.owner, 'retry', {
                '_agent_protocol': 2, 'agent_task_id': 't1', 'agent_run_id': gateway.ids[-1],
            }, [])
            live = await service.resume_session_run(session.id, self.owner)
        else:
            live = await service.start_session_run(
                owner=self.owner, session_id=session.id, prompt='retry', model=None,
                mode='fast', attachments=[], workspace_id=None, skills=[],
                gateway=gateway,
            )
        self.addAsyncCleanup(self.stop_projection, live)
        return session.id, live

    async def stop_projection(self, live):
        if not live.task.done():
            live.task.cancel()
        await asyncio.gather(live.task, return_exceptions=True)

    async def drain(self, response):
        async def collect():
            return [decode(chunk) async for chunk in response.body_iterator]
        return await asyncio.wait_for(collect(), timeout=5)

    def assert_history(self, events, gateway):
        self.assertEqual([index for index, _, _ in events], list(range(len(events))))
        self.assertEqual([data['run_id'] for _, name, data in events if name == 'run_start'],
                         gateway.ids)
        self.assertEqual([data['text'] for _, name, data in events if name == 'delta'],
                         gateway.ids)
        self.assertEqual(sum(name == 'result' for _, name, _ in events), 1)
        self.assertEqual(events[-1][1], 'result')

    async def test_one_two_three_runs_initial_recovery_and_every_after_offset(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                gateway = RetryGateway(count)
                session_id, live = await self.start(gateway)
                original = await self.drain(api.session_run_stream(live))
                self.assert_history(original, gateway)
                # Exercise all intermediate Run and result boundaries, including
                # after=result ID (unreceived) and after=result ID+1 (received).
                for after in range(len(original) + 1):
                    cached = await api.attach_agent_session_run(session_id, after=after, owner=self.owner)
                    self.assertEqual(await self.drain(cached), original[after:])
                    live_runs._live.clear()
                    rebuilt = await api.attach_agent_session_run(session_id, after=after, owner=self.owner)
                    self.assertEqual(await self.drain(rebuilt), original[after:])

    async def test_three_run_result_id_six_uses_next_offset_semantics(self):
        session_id, live = await self.start(RetryGateway())
        events = await self.drain(api.session_run_stream(live))
        self.assertEqual(events[-1][0], 6)
        for after, expected in ((3, events[3:]), (6, [events[-1]]), (7, []), (20, [])):
            with self.subTest(after=after):
                live_runs._live.clear()
                response = await api.attach_agent_session_run(session_id, after=after, owner=self.owner)
                self.assertEqual(await self.drain(response), expected)

    async def check_active_reconnect(self, *, discard_cache, recover=False):
        gateway = RetryGateway(active=True, tail=True)
        session_id, live = await self.start(gateway, recover=recover)
        stream = api.session_run_stream(live).body_iterator
        prefix = [decode(await anext(stream)), decode(await anext(stream))]
        await stream.aclose()
        self.assertFalse(live.done)
        if discard_cache:
            await self.stop_projection(live)
            live_runs._live.clear()
        response = await api.attach_agent_session_run(session_id, after=2, owner=self.owner)
        # r2 fails/times out and r3 finishes between the two r1 polls.
        gateway.ready.set()
        remaining = await self.drain(response)
        combined = prefix + remaining
        self.assertEqual([data['run_id'] for _, name, data in combined if name == 'run_start'],
                         ['r1', 'r2', 'r3'])
        self.assertEqual([data['text'] for _, name, data in combined if name == 'delta'],
                         ['r1', 'tail', 'r2', 'r3'])
        self.assertEqual([index for index, _, _ in combined], list(range(8)))
        self.assertEqual(sum(name == 'result' for _, name, _ in combined), 1)
        live_runs._live.clear()
        rebuilt = await api.attach_agent_session_run(session_id, after=0, owner=self.owner)
        self.assertEqual(await self.drain(rebuilt), combined)

    async def test_active_subscription_reconnect_drains_tail_before_skipped_retries(self):
        await self.check_active_reconnect(discard_cache=False)

    async def test_active_projection_recovers_without_cache(self):
        await self.check_active_reconnect(discard_cache=True)

    async def test_recovery_projection_follows_retries_created_between_polls(self):
        await self.check_active_reconnect(discard_cache=False, recover=True)

    async def test_final_failure_or_timeout_emits_one_stable_result(self):
        for status, expected in (('failed', 'failed'), ('timed_out', 'timeout')):
            with self.subTest(status=status):
                gateway = RetryGateway(final_status=status)
                session_id, live = await self.start(gateway)
                events = await self.drain(api.session_run_stream(live))
                self.assert_history(events, gateway)
                self.assertEqual(events[-1][2]['status'], expected)
                live_runs._live.clear()
                response = await api.attach_agent_session_run(session_id, after=6, owner=self.owner)
                self.assertEqual(await self.drain(response), [events[-1]])

    async def test_cross_owner_cannot_attach_cached_or_reconstructed_stream(self):
        session_id, live = await self.start(RetryGateway())
        await self.drain(api.session_run_stream(live))
        for cached in (True, False):
            with self.subTest(cached=cached):
                if not cached:
                    live_runs._live.clear()
                with self.assertRaises(BusinessError) as error:
                    await api.attach_agent_session_run(session_id, after=0, owner='anon:other')
                self.assertEqual(error.exception.status, 404)


if __name__ == '__main__':
    unittest.main()

"""Real JSONB round trips; opt in with a dedicated, migrated test database."""
from __future__ import annotations

import os
import importlib.util
import unittest
import uuid
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.api import agent as api
from app.core.database import dispose_engine, get_engine, session_scope
from app.main import app
from app.models.agent_session import AgentTurnRow
from app.services.agent_sessions import live as live_runs, service
from app.services.agent_sessions.postgres_repository import PostgresAgentSessionRepository
from tests.test_agent_message_blocks import MessageGateway, make_message, message_events
from tests.test_agent_sse_tail import decode


@unittest.skipUnless(os.getenv('TEST_AGENT_MESSAGE_DATABASE_URL'), 'dedicated message test DB not configured')
class AgentMessagePostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await dispose_engine()
        self.enterContext(patch.dict('os.environ', {
            'CHAT_DATABASE_URL': os.environ['TEST_AGENT_MESSAGE_DATABASE_URL'],
            'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
        }))
        self.owner = f'anon:{uuid.uuid4()}'
        self.repo = PostgresAgentSessionRepository()
        self.enterContext(patch.object(service, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(api, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(live_runs, '_live', {}))

    async def asyncTearDown(self):
        await self.repo.purge_owner(self.owner)
        await dispose_engine()

    async def test_projection_jsonb_reconnect_history_and_replay_are_identical(self):
        original = make_message()
        gateway = MessageGateway(original)
        self.enterContext(patch.object(service, 'agent_gateway', gateway))
        session = await self.repo.create(self.owner, 'JSONB', {})
        live = await service.start_session_run(owner=self.owner, session_id=session.id,
            prompt='q', model=None, mode='fast', attachments=[], workspace_id=None, skills=[], gateway=gateway)
        events = [decode(chunk) async for chunk in api.session_run_stream(live).body_iterator]
        self.assertEqual(events[-1][2]['message'], original)
        async with session_scope() as db:
            row = await db.get(AgentTurnRow, live.turn_id)
            self.assertEqual(row.message, original)
        # Discard all Backend process state and use fresh DB connections/repository.
        await dispose_engine()
        live_runs._live.clear()
        fresh = PostgresAgentSessionRepository()
        self.enterContext(patch.object(service, 'agent_session_repository', fresh))
        self.enterContext(patch.object(api, 'agent_session_repository', fresh))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get(f'/api/v1/agent/sessions/{session.id}', headers={
                'x-shenzhi-anonymous-id': self.owner[5:],
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['turns'][0]['message'], original)
        recovered = await service.resume_session_run(session.id, self.owner)
        replay = [decode(chunk) async for chunk in api.session_run_stream(recovered).body_iterator]
        self.assertEqual(replay, events)
        self.assertEqual([{'name': name, 'data': data} for _, name, data in replay[1:-1]], message_events(original))

    async def test_terminal_statuses_and_legacy_null_round_trip(self):
        session = await self.repo.create(self.owner, 'statuses', {})
        for status in ('done', 'failed', 'stopped', 'timeout', 'awaiting_input'):
            original = make_message(status=status)
            turn, _ = await self.repo.start_turn(session.id, self.owner, 'q', {}, [], worker_id='message-test')
            await self.repo.finish_turn(session.id, self.owner, turn.id,
                {'status': status, 'message': original, 'assistant_content': 'legacy text'}, worker_id='message-test')
            loaded = (await self.repo.get(session.id, self.owner)).turns[-1]
            self.assertEqual(loaded.public()['message'], original)
            original['blocks'].clear()
            self.assertEqual((await self.repo.get(session.id, self.owner)).turns[-1].message, make_message(status=status))
        legacy, _ = await self.repo.start_turn(session.id, self.owner, 'old', {}, [], worker_id='message-test')
        await self.repo.finish_turn(session.id, self.owner, legacy.id,
            {'status': 'done', 'assistant_content': '原有正文  \n'}, worker_id='message-test')
        await dispose_engine()
        loaded = (await PostgresAgentSessionRepository().get(session.id, self.owner)).turns[-1]
        self.assertIsNone(loaded.public()['message'])
        self.assertEqual(loaded.assistant_content, '原有正文  \n')
        async with session_scope() as db:
            self.assertTrue((await db.execute(text('SELECT message IS NULL FROM agent_turns WHERE id=:id'),
                                              {'id': legacy.id})).scalar_one())

    async def test_invalid_snapshot_does_not_partially_finish_turn(self):
        session = await self.repo.create(self.owner, 'invalid', {})
        turn, _ = await self.repo.start_turn(session.id, self.owner, 'q', {}, [], worker_id='message-test')
        invalid = deepcopy(make_message())
        invalid['references'] = []
        with self.assertRaises(ValueError):
            await self.repo.finish_turn(session.id, self.owner, turn.id,
                {'status': 'done', 'message': invalid}, worker_id='message-test')
        loaded = (await self.repo.get(session.id, self.owner)).turns[-1]
        self.assertEqual(loaded.status, 'running')
        self.assertIsNone(loaded.message)

    async def test_actual_migration_preserves_legacy_rows_without_backfilling(self):
        path = Path(__file__).resolve().parents[1] / 'migrations/versions/029_agent_message.py'
        spec = importlib.util.spec_from_file_location('agent_message_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        schema = f'message_migration_{uuid.uuid4().hex}'
        # Transactional DDL in a fresh schema: a failure rolls back this fixture.
        async with get_engine().begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.execute(text('CREATE TABLE agent_turns (id text PRIMARY KEY, assistant_content text NOT NULL)'))
            await connection.execute(text('INSERT INTO agent_turns VALUES (:id, :content)'),
                                     {'id': 'old-turn', 'content': '迁移前正文  \r\n'})

            def upgrade(sync_connection):
                with patch.object(migration, 'op', Operations(MigrationContext.configure(sync_connection))):
                    migration.upgrade()

            await connection.run_sync(upgrade)
            row = (await connection.execute(text('SELECT id, assistant_content, message FROM agent_turns'))).one()
            self.assertEqual(tuple(row), ('old-turn', '迁移前正文  \r\n', None))
            await connection.execute(text('DROP TABLE agent_turns'))
            await connection.execute(text(f'DROP SCHEMA "{schema}"'))

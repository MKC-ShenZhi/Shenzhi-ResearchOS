import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.agent_entitlements.admin import list_audit


class AuditAccountsTests(unittest.IsolatedAsyncioTestCase):
    def row(self, key, payload):
        return SimpleNamespace(operation_id=key, principal='local-admin:admin', reason='test',
                               created_at=datetime(2026, 11, 20, tzinfo=timezone.utc), payload=payload)

    async def test_batch_email_lookup_keeps_missing_accounts_and_original_payload(self):
        payload = {'action': 'assign', 'request': {'user_ids': ['existing', 'deleted', 'existing']}}
        rows = [self.row('assign', payload), self.row('legacy', {'owner_id': 'user:existing'}),
                self.row('publish', {'action': 'publish'})]
        db = MagicMock()
        db.scalars = AsyncMock(return_value=MagicMock())
        db.scalars.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=MagicMock())
        db.execute.return_value.mappings.return_value.all.return_value = [
            {'id': 'existing', 'email': 'current@example.com'}]
        result = await list_audit(db, page=1, page_size=20)
        self.assertEqual(result['items'][0]['target_accounts'], [
            {'user_id': 'existing', 'email': 'current@example.com'},
            {'user_id': 'deleted', 'email': None}])
        self.assertEqual(result['items'][1]['target_accounts'], [
            {'user_id': 'existing', 'email': 'current@example.com'}])
        self.assertEqual(result['items'][2]['target_accounts'], [])
        self.assertEqual(payload['request']['user_ids'], ['existing', 'deleted', 'existing'])
        self.assertIs(result['items'][0]['payload'], payload)
        db.execute.assert_awaited_once()
        self.assertEqual(db.execute.call_args.args[1], {'ids': ['deleted', 'existing']})

    async def test_no_account_lookup_for_unattributed_records(self):
        db = MagicMock()
        db.scalars = AsyncMock(return_value=MagicMock())
        db.scalars.return_value.all.return_value = [
            self.row('reconcile', {'action': 'reconcile-close'}),
            self.row('invalid', {'request': {'user_ids': 'invalid'}})]
        db.execute = AsyncMock(return_value=MagicMock())
        result = await list_audit(db, page=2, page_size=20)
        self.assertEqual(result['page'], 2)
        self.assertTrue(all(item['target_accounts'] == [] for item in result['items']))
        db.execute.assert_not_awaited()

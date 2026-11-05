"""Regression: an upstream deletion must not block all conference updates."""
import copy
import unittest
from datetime import datetime, timezone
from app.services.conferences import ConferenceDeadlineService, ConferenceFilters, catalog_from_snapshot
from app.services.conferences.repository import retain_followed_conferences
from app.services.conferences.sync import validate_replacement
from app.schemas.conferences import ConferenceSnapshotFile
from tests.test_conferences import snapshot, conference, edition

class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.old = snapshot(*[conference('ai-'+str(i), edition(2027, {'deadline': '2027-12-01 00:00:00'})) for i in range(10)])
        self.new = copy.deepcopy(self.old)
        self.new['snapshot_id'] = 'upstream-new'
        self.new['conferences'] = self.new['conferences'][1:]

    def test_followed_deletion_keeps_last_record_without_blocking_update(self):
        with self.assertLogs('app.services.conferences.sync', 'WARNING'):
            self.assertEqual(validate_replacement(self.new, self.old, {'ai-0'}), ['ai-0'])
        merged = retain_followed_conferences(self.new, self.old, {'ai-0'})
        self.assertEqual(len(merged['conferences']), 10)
        self.assertTrue(merged['conferences'][-1]['source_removed'])
        self.assertNotEqual(merged['snapshot_id'], self.new['snapshot_id'])
        self.assertNotIn('source_removed', self.old['conferences'][0])
        self.assertEqual(len(self.new['conferences']), 9)

    def test_removed_conference_has_no_active_countdown_and_cannot_be_newly_followed(self):
        merged = retain_followed_conferences(self.new, self.old, {'ai-0'})
        catalog = catalog_from_snapshot(ConferenceSnapshotFile.model_validate(merged))
        service = ConferenceDeadlineService(now_provider=lambda: datetime(2026,11,5,tzinfo=timezone.utc))
        item = service.deadlines(ConferenceFilters(ids=frozenset({'ai-0'})), catalog=catalog).items[0]
        self.assertTrue(item.source_removed)
        self.assertIsNone(item.next_milestone)
        self.assertEqual(item.status, 'closed')
        self.assertFalse(service.has_conference('ai-0', catalog=catalog))

    def test_unfollowed_removed_record_drops_and_restored_record_is_active(self):
        merged = retain_followed_conferences(self.new, self.old, {'ai-0'})
        pruned = retain_followed_conferences(self.new, merged, set())
        self.assertNotIn('ai-0', {i['id'] for i in pruned['conferences']})
        restored = retain_followed_conferences(self.old, merged, {'ai-0'})
        self.assertFalse(restored['conferences'][0].get('source_removed', False))

    def test_retained_records_do_not_inflate_shrink_protection_baseline(self):
        previous = copy.deepcopy(self.old)
        previous['conferences'] += [{**self.old['conferences'][0], 'id':'ai-old-'+str(i), 'source_removed':True} for i in range(20)]
        with self.assertLogs('app.services.conferences.sync', 'WARNING'):
            validate_replacement(self.new, previous, set())
        smaller = copy.deepcopy(self.new)
        smaller['conferences'].pop()
        with self.assertRaisesRegex(ValueError, '10%'):
            validate_replacement(smaller, previous, set())

    def test_unknown_legacy_follow_does_not_block_valid_catalog(self):
        with self.assertLogs('app.services.conferences.repository', 'WARNING'):
            result = retain_followed_conferences(self.new, self.old, {'missing-legacy-id'})
        self.assertEqual(result, self.new)

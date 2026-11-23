import os
import unittest
from types import SimpleNamespace

from sqlalchemy import delete, select

from app.core.database import session_scope
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.schemas.knowledge import PaperSearchResult, Provenance
from app.services.discovery_pool.sync import (
    DiscoveryPoolSync,
    PoolSyncError,
    displayable_image_id,
    pool_row,
)
from app.services.knowledge.service import KnowledgeServiceError

# Far from any real pool year, so the persistence tests never touch synced data.
YEAR = 1901
ABSTRACT = 'A displayable abstract. ' * 12
TOPIC = {'id': 'openalex:topic:T10028', 'nameZh': None, 'nameEn': 'Language models'}


def paper(paper_id, **changes):
    values = {
        'id': paper_id, 'image_id': f'/images/V_{YEAR}/{paper_id.replace(":", "-")}.png',
        'title': f'Paper title {paper_id}', 'abstract': ABSTRACT, 'authors': ['Ada Lovelace'],
        'year': YEAR, 'subjects': ['RAG'], 'keywords': ['retrieval'],
        'provenance': Provenance(external_id=paper_id),
    }
    values.update(changes)
    return PaperSearchResult(**values)


class FakeKnowledge:
    """Serves fixed venues page by page; `failures` makes (venue, offset) fail that many times."""

    def __init__(self, venues, failures=None):
        self.venues = venues
        self.failures = dict(failures or {})
        self.requests = []

    async def conferences(self):
        return SimpleNamespace(items=[SimpleNamespace(name=name, years=[YEAR]) for name in self.venues]
                               + [SimpleNamespace(name='Other year', years=[YEAR - 1])])

    async def browse_papers(self, request):
        key = (request.conference, request.offset)
        self.requests.append(key)
        if self.failures.get(key, 0) > 0:
            self.failures[key] -= 1
            raise KnowledgeServiceError('unavailable')
        papers = self.venues[request.conference]
        return SimpleNamespace(results=papers[request.offset:request.offset + request.limit], total=len(papers))


class PoolRuleTests(unittest.TestCase):
    def test_only_images_the_web_proxy_serves_are_displayable(self):
        self.assertTrue(displayable_image_id('/images/CVPR_2026/2605.1v1.png'))
        self.assertTrue(displayable_image_id('/images/a/b.JPEG'))
        for rejected in (None, '', '/images/ICLR_2026/x.svg', '/images/../secret.png',
                         '/img/x.png', '/images/a b.png', '/images/.hidden.png', '/images/'):
            self.assertFalse(displayable_image_id(rejected), rejected)

    def test_rejections_name_the_reason_and_rows_are_cleaned(self):
        self.assertEqual(pool_row(paper('p', image_id=None), 'V', YEAR), (None, 'image_missing'))
        self.assertEqual(pool_row(paper('p', image_id='/images/x.svg'), 'V', YEAR), (None, 'image_format'))
        self.assertEqual(pool_row(paper('p', year=YEAR + 1), 'V', YEAR), (None, 'year'))
        self.assertEqual(pool_row(paper('p', abstract='short'), 'V', YEAR), (None, 'abstract'))
        self.assertEqual(pool_row(paper('p', authors=['MIT University']), 'V', YEAR), (None, 'authors'))
        self.assertEqual(pool_row(paper('p', title='1 Introduction'), 'V', YEAR), (None, 'title'))
        row, reason = pool_row(paper('p', title='  A   spaced   title  ', primary_subject=' model pruning ',
                                     subjects=['RAG', 'CVPR.2024 - Accept', 'RAG'],
                                     topics=[TOPIC]), 'Venue', YEAR)
        self.assertIsNone(reason)
        self.assertEqual((row['title'], row['venue'], row['year']), ('A spaced title', 'Venue', YEAR))
        # Venue labels and duplicates are not topics; the main subject is kept for edition balance.
        self.assertEqual((row['subjects'], row['primary_subject']), (['RAG'], 'model pruning'))
        self.assertEqual(row['topics'], [TOPIC])


class PoolCollectTests(unittest.IsolatedAsyncioTestCase):
    async def test_walks_every_page_of_every_year_venue_and_dedupes(self):
        knowledge = FakeKnowledge({
            'A': [paper(f'a:{index}') for index in range(230)],
            'B': [paper('a:0'), paper('b:svg', image_id='/images/x.svg')],
        })
        rows, result = await DiscoveryPoolSync(knowledge, retry_delay=0).collect(YEAR)
        self.assertEqual(sorted(knowledge.requests), [('A', 0), ('A', 100), ('A', 200), ('B', 0)])
        self.assertEqual(len(rows), 230)
        self.assertEqual((result.venues, result.fetched, result.accepted), (2, 232, 230))
        self.assertEqual(result.rejected, {'duplicate': 1, 'image_format': 1})

    async def test_transient_page_failures_are_retried(self):
        knowledge = FakeKnowledge({'A': [paper('a:0')]}, failures={('A', 0): 2})
        rows, _ = await DiscoveryPoolSync(knowledge, retry_delay=0).collect(YEAR)
        self.assertEqual(len(rows), 1)

    async def test_a_page_that_keeps_failing_aborts_the_whole_run(self):
        knowledge = FakeKnowledge({'A': [paper(f'a:{index}') for index in range(150)]}, failures={('A', 100): 3})
        with self.assertRaises(PoolSyncError):
            await DiscoveryPoolSync(knowledge, retry_delay=0).collect(YEAR)


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class PoolPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        await self._clear()

    async def asyncTearDown(self):
        from app.core.database import dispose_engine
        await self._clear()
        # The engine's connections belong to this test's loop; later tests run on other loops.
        await dispose_engine()

    @staticmethod
    async def _clear():
        async with session_scope() as session:
            await session.execute(delete(DiscoveryPoolPaperRow).where(DiscoveryPoolPaperRow.year == YEAR))

    @staticmethod
    async def _ids():
        async with session_scope() as session:
            return set(await session.scalars(select(DiscoveryPoolPaperRow.paper_id).where(
                DiscoveryPoolPaperRow.year == YEAR,
            )))

    async def test_sync_replaces_the_year_and_refuses_suspicious_shrinks(self):
        first = [paper(f'p:{index}') for index in range(10)]
        result = await DiscoveryPoolSync(FakeKnowledge({'A': first}), retry_delay=0).sync(YEAR)
        self.assertEqual((result.previous, result.accepted, result.removed), (0, 10, 0))
        self.assertEqual(await self._ids(), {f'p:{index}' for index in range(10)})

        # A dry run reports but never writes.
        dry = await DiscoveryPoolSync(FakeKnowledge({'A': first[:6]}), retry_delay=0).sync(YEAR, dry_run=True)
        self.assertEqual((dry.previous, dry.accepted, dry.removed), (10, 6, None))
        self.assertEqual(len(await self._ids()), 10)

        # Updated metadata is applied, unseen papers removed, other years untouched.
        renamed = [paper('p:0', title='Renamed paper', topics=[TOPIC])] + first[1:6] + [paper('p:new')]
        result = await DiscoveryPoolSync(FakeKnowledge({'A': renamed}), retry_delay=0).sync(YEAR)
        self.assertEqual((result.previous, result.accepted, result.removed), (10, 7, 4))
        self.assertEqual(await self._ids(), {f'p:{index}' for index in range(6)} | {'p:new'})
        async with session_scope() as session:
            row = await session.get(DiscoveryPoolPaperRow, 'p:0')
            self.assertEqual((row.title, row.paper_fields()['topics']), ('Renamed paper', [TOPIC]))

        # Losing more than half at once looks like an outage: the pool is kept.
        with self.assertRaises(PoolSyncError):
            await DiscoveryPoolSync(FakeKnowledge({'A': first[:3]}), retry_delay=0).sync(YEAR)
        self.assertEqual(len(await self._ids()), 7)

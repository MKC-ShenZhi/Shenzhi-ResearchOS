import os
import unittest
from collections import Counter
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete

from app.core.database import session_scope
from app.models.daily_recommendation import DailyRecommendationRow
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.schemas.discovery import DiscoveryPaper
from app.services import discovery
from app.services.discovery import DiscoveryCandidate, DiscoverySnapshot, load_stored_edition
from app.services.discovery_pool import edition as edition_module
from app.services.discovery_pool.edition import (
    SCREEN_SIZE,
    VENUE_PER_SCREEN,
    DailyEditionBuilder,
    EditionError,
)

DAY = date(2026, 11, 2)
VENUES = ('AAAI', 'ACL', 'CVPR', 'ICLR', 'ICML', 'ECCV')


def curated_snapshot(count=10):
    return DiscoverySnapshot('seed-test', tuple(DiscoveryCandidate(DiscoveryPaper(
        id=f'curated:{index}', title=f'Curated {index}', abstract='a', year=2026,
        venue=VENUES[index % len(VENUES)], thumbnail_url=f'/paper-thumbnails/c{index}.webp',
    ), 1) for index in range(count)))


def pool_row(paper_id, venue, year=2026):
    return SimpleNamespace(paper_id=paper_id, title=f'Title {paper_id}', abstract='abstract', authors=['A'],
                           year=year, venue=venue, image_id=f'/images/{paper_id.replace(":", "-")}.png',
                           keywords=[f'kw-{paper_id}'], subjects=['RAG'])


def pool(count, venues=VENUES):
    return [pool_row(f'pool:{index}', venues[index % len(venues)]) for index in range(count)]


def builder(rows, *, last_shown=None, popularity=None, curated=None):
    built = DailyEditionBuilder(lambda: curated or curated_snapshot())
    built._inputs = AsyncMock(return_value=(2026, rows, last_shown or {}, popularity or {}, 0))
    return built


@patch.multiple(edition_module, CURATED_PER_EDITION=6, POPULAR_PER_EDITION=3)
class EditionRuleTests(unittest.IsolatedAsyncioTestCase):
    async def test_sections_first_screen_and_popularity_order(self):
        popularity = {'pool:5': 9, 'pool:7': 30, 'pool:9': 4, 'missing:1': 50}
        result = await builder(pool(200), popularity=popularity).build(DAY, size=36)
        self.assertEqual(result.sections, {'curated': 6, 'popular': 3, 'explore': 27})
        ids = [paper.id for paper in result.papers]
        self.assertEqual(len(ids), len(set(ids)))
        # Popular papers in the pool, most liked/collected first; unknown ids ignored.
        popular = [paper_id for paper_id in ids if paper_id in popularity]
        self.assertEqual(popular, ['pool:7', 'pool:5', 'pool:9'])
        # The first screen leads with every hand-picked paper.
        self.assertEqual(sum(paper_id.startswith('curated:') for paper_id in ids[:SCREEN_SIZE]), 6)

    async def test_least_recently_shown_first_and_stable_per_day(self):
        rows = pool(60)
        shown = {f'pool:{index}': DAY - timedelta(days=1) for index in range(30)}
        result = await builder(rows, last_shown=shown).build(DAY, size=30)
        explore = [paper.id for paper in result.papers if paper.id.startswith('pool:')]
        self.assertTrue(set(explore).isdisjoint(shown))
        again = await builder(rows, last_shown=shown).build(DAY, size=30)
        self.assertEqual(result.edition_id, again.edition_id)
        tomorrow = await builder(rows, last_shown=shown).build(DAY + timedelta(days=1), size=30)
        self.assertNotEqual([p.id for p in result.papers], [p.id for p in tomorrow.papers])

    async def test_curated_rotation_prefers_papers_not_shown_recently(self):
        shown = {f'curated:{index}': DAY - timedelta(days=1) for index in range(6)}
        result = await builder(pool(50), last_shown=shown).build(DAY, size=20)
        curated = {paper.id for paper in result.papers if paper.id.startswith('curated:')}
        # All four unseen picks first; the remaining slots go to the recently shown.
        self.assertEqual(len(curated), 6)
        self.assertTrue({'curated:6', 'curated:7', 'curated:8', 'curated:9'} <= curated)

    async def test_venue_share_and_per_screen_spread(self):
        rows = [pool_row(f'a:{index}', 'AAAI') for index in range(200)] + pool(60, VENUES[1:])
        result = await builder(rows, curated=curated_snapshot(0)).build(DAY, size=40)
        self.assertEqual(len(result.papers), 40)
        self.assertLessEqual(Counter(paper.venue for paper in result.papers)['AAAI'], 10)
        for start in range(0, 40, SCREEN_SIZE):
            screen = Counter(paper.venue for paper in result.papers[start:start + SCREEN_SIZE])
            self.assertLessEqual(max(screen.values()), VENUE_PER_SCREEN)

    async def test_single_venue_pool_still_fills_the_edition(self):
        rows = [pool_row(f'a:{index}', 'AAAI') for index in range(50)]
        result = await builder(rows, curated=curated_snapshot(0)).build(DAY, size=30)
        self.assertEqual(len(result.papers), 30)

    async def test_curated_papers_in_the_pool_keep_static_thumbnails(self):
        rows = pool(30) + [pool_row('curated:3', 'ACL')]
        result = await builder(rows).build(DAY, size=30)
        by_id = {paper.id: paper for paper in result.papers}
        self.assertEqual(by_id['curated:3'].thumbnail_url, '/paper-thumbnails/c3.webp')
        self.assertIsNone(by_id['curated:3'].image_id)
        # The packaged snapshot has no topics; the pool supplies them for the card.
        self.assertEqual(by_id['curated:3'].keywords, ['kw-curated:3'])
        others = [paper for paper_id, paper in by_id.items() if paper_id.startswith('curated:') and paper_id != 'curated:3']
        self.assertTrue(others)
        self.assertTrue(all(paper.keywords == [] for paper in others))
        pool_paper = next(paper for paper in result.papers if paper.id.startswith('pool:'))
        self.assertIsNone(pool_paper.thumbnail_url)
        self.assertTrue(pool_paper.image_id.startswith('/images/'))
        self.assertEqual((pool_paper.keywords, pool_paper.subjects), ([f'kw-{pool_paper.id}'], ['RAG']))

    async def test_empty_pool_is_refused(self):
        with self.assertRaises(EditionError):
            await builder([]).build(DAY)


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class EditionPersistenceTests(unittest.IsolatedAsyncioTestCase):
    # Far from real pool years and edition dates.
    YEAR = 1902
    START = date(2001, 1, 1)

    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        discovery._edition_cache.clear()
        await self._clear()

    async def asyncTearDown(self):
        await self._clear()
        discovery._edition_cache.clear()

    async def _clear(self):
        async with session_scope() as session:
            await session.execute(delete(DiscoveryPoolPaperRow).where(DiscoveryPoolPaperRow.year == self.YEAR))
            await session.execute(delete(DailyRecommendationRow).where(
                DailyRecommendationRow.recommendation_date.between(self.START, self.START + timedelta(days=30)),
            ))

    async def test_published_editions_are_served_and_never_repeat_while_the_pool_lasts(self):
        async with session_scope() as session:
            session.add_all(DiscoveryPoolPaperRow(
                **{key: value for key, value in vars(pool_row(f'persist:{index}', VENUES[index % 6], self.YEAR)).items()},
                synced_at=discovery.utc_now(),
            ) for index in range(40))
            # A legacy payload from the retired feature must neither break history nor be served.
            session.add(DailyRecommendationRow(recommendation_date=self.START, payload=[{'legacy': True}]))
        self.assertIsNone(await load_stored_edition(self.START))

        builder = DailyEditionBuilder(lambda: curated_snapshot(0))
        seen: set[str] = set()
        for offset in (1, 2, 3, 4):
            day = self.START + timedelta(days=offset)
            result = await builder.publish(day, size=10, year=self.YEAR)
            ids = {paper.id for paper in result.papers}
            self.assertTrue(ids.isdisjoint(seen))
            seen |= ids
            stored = await load_stored_edition(day)
            self.assertEqual(stored.list_id, result.edition_id)
            self.assertEqual([paper.id for paper in stored.papers], [paper.id for paper in result.papers])
        self.assertEqual(len(seen), 40)
        # Once the pool is exhausted, the least recently shown papers return first.
        fifth = await builder.build(self.START + timedelta(days=5), size=10, year=self.YEAR)
        first_day = {paper.id for paper in (await load_stored_edition(self.START + timedelta(days=1))).papers}
        self.assertEqual({paper.id for paper in fifth.papers}, first_day)
        # Re-publishing a day replaces it in place.
        again = await builder.publish(self.START + timedelta(days=4), size=10, year=self.YEAR)
        self.assertEqual(again.edition_id, result.edition_id)

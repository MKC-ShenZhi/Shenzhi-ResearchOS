import os
import unittest
from collections import Counter
from datetime import date, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import delete

from app.core.database import session_scope
from app.models.daily_recommendation import DailyRecommendationRow
from app.models.discovery_pool import DiscoveryPoolPaperRow
from app.services import discovery
from app.services.discovery import load_latest_edition
from app.services.discovery_pool.edition import HISTORY_DAYS, DailyEditionBuilder, EditionError
from app.services.home_feed.config import SCREEN_SIZE, VENUE_PER_SCREEN

DAY = date(2026, 11, 2)
VENUES = ('AAAI', 'ACL', 'CVPR', 'ICLR', 'ICML', 'ECCV')
ABSTRACT = 'A displayable abstract for the home card. ' * 6


def pool_row(paper_id, venue, year=2026, subject=None, **changes):
    values = dict(
        paper_id=paper_id, title=f'Title {paper_id}', abstract=ABSTRACT, authors=['Ada Lovelace'],
        year=year, venue=venue, image_id=f'/images/{paper_id.replace(":", "-")}.png',
        keywords=[f'kw-{paper_id}'], subjects=['RAG'], primary_subject=subject,
    )
    values.update(changes)
    return DiscoveryPoolPaperRow(**values)


def pool(count, venues=VENUES, **changes):
    return [pool_row(f'pool:{index}', venues[index % len(venues)], **changes) for index in range(count)]


def builder(rows, *, last_shown=None):
    built = DailyEditionBuilder()
    built._inputs = AsyncMock(return_value=(2026, rows, last_shown or {}, 0))
    return built


class EditionRuleTests(unittest.IsolatedAsyncioTestCase):
    async def test_least_recently_shown_first_and_stable_per_day(self):
        rows = pool(60)
        shown = {f'pool:{index}': DAY - timedelta(days=1) for index in range(30)}
        result = await builder(rows, last_shown=shown).build(DAY, size=30)
        self.assertTrue({paper.id for paper in result.papers}.isdisjoint(shown))
        again = await builder(rows, last_shown=shown).build(DAY, size=30)
        self.assertEqual(result.edition_id, again.edition_id)
        tomorrow = await builder(rows, last_shown=shown).build(DAY + timedelta(days=1), size=30)
        self.assertNotEqual([p.id for p in result.papers], [p.id for p in tomorrow.papers])

    async def test_edition_is_pool_papers_only_with_knowledge_images_and_topics(self):
        result = await builder(pool(30)).build(DAY, size=30)
        self.assertEqual(len(result.papers), 30)
        for paper in result.papers:
            self.assertIsNone(paper.thumbnail_url)
            self.assertTrue(paper.image_id.startswith('/images/'))
            self.assertEqual((paper.keywords, paper.subjects), ([f'kw-{paper.id}'], ['RAG']))

    async def test_rule_b_rejects_papers_a_card_cannot_show(self):
        rows = pool(20) + [
            pool_row('bad:title', 'ACL', title='1 Introduction'),
            pool_row('bad:abstract', 'ACL', abstract='too short'),
            pool_row('bad:image', 'ACL', image_id='/images/x/figure.svg'),
        ]
        result = await builder(rows).build(DAY, size=30)
        self.assertFalse({paper.id for paper in result.papers} & {'bad:title', 'bad:abstract', 'bad:image'})
        self.assertEqual(result.rejected, {'title': 1, 'abstract': 1, 'image_format': 1})

    async def test_venue_share_and_per_screen_spread(self):
        rows = [pool_row(f'a:{index}', 'AAAI') for index in range(200)] + pool(60, VENUES[1:])
        result = await builder(rows).build(DAY, size=40)
        self.assertEqual(len(result.papers), 40)
        self.assertLessEqual(Counter(paper.venue for paper in result.papers)['AAAI'], 10)
        for start in range(0, 40, SCREEN_SIZE):
            screen = Counter(paper.venue for paper in result.papers[start:start + SCREEN_SIZE])
            self.assertLessEqual(max(screen.values()), VENUE_PER_SCREEN)

    async def test_primary_subject_share_is_capped_among_equally_fresh_papers(self):
        rows = pool(200, subject='diffusion models') + [
            pool_row(f'other:{index}', VENUES[index % 6], subject=f'subject {index}') for index in range(60)
        ]
        result = await builder(rows).build(DAY, size=60)
        subjects = Counter('diffusion' if paper.id.startswith('pool:') else 'other' for paper in result.papers)
        self.assertEqual(subjects['diffusion'], 3)  # 5% of 60

    async def test_single_venue_pool_still_fills_the_edition(self):
        rows = [pool_row(f'a:{index}', 'AAAI', subject='same') for index in range(50)]
        result = await builder(rows).build(DAY, size=30)
        self.assertEqual(len(result.papers), 30)

    async def test_empty_or_fully_rejected_pool_is_refused(self):
        with self.assertRaises(EditionError):
            await builder([]).build(DAY)
        with self.assertRaises(EditionError):
            await builder(pool(5, abstract='short')).build(DAY)


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
        from app.core.database import dispose_engine
        await self._clear()
        discovery._edition_cache.clear()
        await dispose_engine()

    async def _clear(self):
        async with session_scope() as session:
            await session.execute(delete(DiscoveryPoolPaperRow).where(DiscoveryPoolPaperRow.year == self.YEAR))
            await session.execute(delete(DailyRecommendationRow).where(
                DailyRecommendationRow.recommendation_date.between(self.START, self.START + timedelta(days=30)),
            ))

    async def test_published_editions_are_served_and_never_repeat_while_the_pool_lasts(self):
        async with session_scope() as session:
            for index in range(40):
                row = pool_row(f'persist:{index}', VENUES[index % 6], self.YEAR)
                row.synced_at = discovery.utc_now()
                session.add(row)
            # A legacy payload from the retired feature must neither break history nor be served.
            session.add(DailyRecommendationRow(recommendation_date=self.START, payload=[{'legacy': True}]))
        self.assertEqual(await load_latest_edition(self.START), ())

        builder = DailyEditionBuilder()
        seen: set[str] = set()
        for offset in (1, 2, 3, 4):
            day = self.START + timedelta(days=offset)
            result = await builder.publish(day, size=10, year=self.YEAR)
            ids = {paper.id for paper in result.papers}
            self.assertTrue(ids.isdisjoint(seen))
            seen |= ids
            stored = await load_latest_edition(day)
            self.assertEqual([paper.id for paper in stored], [paper.id for paper in result.papers])
        self.assertEqual(len(seen), 40)
        # Once the pool is exhausted, the least recently shown papers return first.
        fifth = await builder.build(self.START + timedelta(days=5), size=10, year=self.YEAR)
        discovery._edition_cache.clear()
        first_day = {paper.id for paper in await load_latest_edition(self.START + timedelta(days=1))}
        self.assertEqual({paper.id for paper in fifth.papers}, first_day)
        # Re-publishing a day replaces it in place.
        again = await builder.publish(self.START + timedelta(days=4), size=10, year=self.YEAR)
        self.assertEqual(again.edition_id, result.edition_id)

    async def test_latest_edition_is_reused_for_a_week_then_dropped(self):
        async with session_scope() as session:
            for index in range(12):
                row = pool_row(f'persist:{index}', VENUES[index % 6], self.YEAR)
                row.synced_at = discovery.utc_now()
                session.add(row)
        published = await DailyEditionBuilder().publish(self.START, size=12, year=self.YEAR)
        ids = [paper.id for paper in published.papers]
        self.assertEqual([paper.id for paper in await load_latest_edition(self.START + timedelta(days=7))], ids)
        self.assertEqual(await load_latest_edition(self.START + timedelta(days=8)), ())

    async def test_purge_keeps_only_editions_inside_the_history_window(self):
        async with session_scope() as session:
            for offset in (0, 1):
                session.add(DailyRecommendationRow(recommendation_date=self.START + timedelta(days=offset), payload=[]))
        deleted = await DailyEditionBuilder.purge(self.START + timedelta(days=HISTORY_DAYS + 1))
        self.assertEqual(deleted, 1)
        async with session_scope() as session:
            kept = await session.get(DailyRecommendationRow, self.START + timedelta(days=1))
        self.assertIsNotNone(kept)

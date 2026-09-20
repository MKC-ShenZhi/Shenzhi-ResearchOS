import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.knowledge import PaperSummary, Provenance
from app.services.reading_history import ReadingHistoryService


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    async def scalars(self, statement):
        self.statement = statement
        limit = statement._limit_clause.value if statement._limit_clause is not None else None
        return FakeScalars(self.rows[:limit] if limit is not None else self.rows)


class BatchKnowledge:
    def __init__(self, missing=()):
        self.missing = set(missing)
        self.requested_ids = []

    async def batch_get_papers(self, paper_ids):
        self.requested_ids.append(list(paper_ids))
        return [
            PaperSummary(
                id=paper_id,
                title=f"Paper {paper_id}",
                authors=[f"Author {paper_id}"],
                venue="Venue A" if paper_id.endswith("a") else "Venue B",
                year=2026,
                abstract="Abstract",
                provenance=Provenance(external_id=paper_id),
            )
            for paper_id in paper_ids
            if paper_id not in self.missing
        ]


class ReadingHistoryListTests(unittest.IsolatedAsyncioTestCase):
    def make_rows(self, count=120):
        now = datetime.now(timezone.utc)
        return [
            SimpleNamespace(
                id=index + 1,
                paper_id=f"paper-{index + 1}",
                last_viewed_at=now - timedelta(minutes=index),
            )
            for index in range(count)
        ]

    async def run_list(self, rows, page=1, page_size=20, query="", missing=()):
        session = FakeSession(rows)

        @asynccontextmanager
        async def fake_scope():
            yield session

        knowledge = BatchKnowledge(missing=missing)
        with patch("app.services.reading_history.session_scope", fake_scope):
            response = await ReadingHistoryService(knowledge).list(
                "user-1", page, page_size, query,
            )
        return response, session, knowledge

    async def test_limits_database_query_to_recent_100_rows(self):
        response, session, knowledge = await self.run_list(self.make_rows())

        self.assertEqual(session.statement._limit_clause.value, 100)
        self.assertEqual(response.total, 100)
        self.assertEqual(len(response.items), 20)
        self.assertEqual(knowledge.requested_ids, [[f"paper-{index}" for index in range(1, 21)]])

    async def test_page_five_returns_rows_81_to_100_in_order(self):
        response, _, knowledge = await self.run_list(self.make_rows(), page=5)

        self.assertEqual([item.paper_id for item in response.items], [f"paper-{index}" for index in range(81, 101)])
        self.assertEqual(response.total, 100)
        self.assertEqual(knowledge.requested_ids, [[f"paper-{index}" for index in range(81, 101)]])

    async def test_search_only_scans_recent_100_then_paginates(self):
        response, session, knowledge = await self.run_list(self.make_rows(), query="paper-9")

        self.assertEqual(session.statement._limit_clause.value, 100)
        self.assertEqual(response.total, 11)
        self.assertEqual([item.paper_id for item in response.items], ["paper-9"] + [f"paper-{index}" for index in range(90, 100)])
        self.assertEqual(len(knowledge.requested_ids[0]), 100)

    async def test_blank_queries_are_unfiltered(self):
        whitespace, _, whitespace_knowledge = await self.run_list(self.make_rows(), query="   ")
        empty, _, empty_knowledge = await self.run_list(self.make_rows(), query="")

        self.assertEqual([item.paper_id for item in whitespace.items], [item.paper_id for item in empty.items])
        self.assertEqual(whitespace.total, empty.total)
        self.assertEqual(len(whitespace_knowledge.requested_ids[0]), 20)
        self.assertEqual(len(empty_knowledge.requested_ids[0]), 20)

    async def test_missing_papers_are_skipped_without_failing(self):
        response, _, knowledge = await self.run_list(
            self.make_rows(), missing=("paper-2", "paper-4"),
        )

        self.assertEqual(response.total, 100)
        self.assertEqual([item.paper_id for item in response.items], ["paper-1", "paper-3"] + [f"paper-{index}" for index in range(5, 21)])
        self.assertEqual(len(knowledge.requested_ids[0]), 20)


if __name__ == "__main__":
    unittest.main()
"""Offline source, guarded sync, bounded transport, cache and scheduler regression tests."""

import asyncio
import copy
import io
import os
import tarfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
import yaml
from app.integrations.conferences.client import ConferenceGitHubClient, conference_files
from app.services.conferences import catalog_from_snapshot, ConferenceDeadlineService
from app.schemas.conferences import ConferenceSnapshotFile
from app.services.conferences_source import snapshot_from_files
from app.services.conferences_sync import ConferenceSync, validate_replacement
from app.services.conferences_repository import ConferenceCatalogCache
from tests.test_conferences import snapshot, conference, edition

SHA = "a" * 40
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


def files():
    return {
        "conference/types.yml": b"- sub: AI\n  name: Artificial Intelligence\n",
        "conference/AI/demo.yml": b"""- title: DEMO
  description: Demo Conference
  sub: AI
  rank: {ccf: A}
  confs:
    - year: 2027
      timezone: AoE
      timeline:
        - deadline: 2026-12-01 23:59:59
          rebuttal_deadline: 2027-01-01 00:00:00
          decision_deadline: TBD
""",
    }


def payload():
    return snapshot_from_files(files(), SHA, "2026-11-03")


def archive(name="repo/conference/AI/demo.yml", kind=tarfile.REGTYPE):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        entry = tarfile.TarInfo(name)
        entry.type = kind
        entry.size = 1 if kind == tarfile.REGTYPE else 0
        tar.addfile(entry, io.BytesIO(b"x") if entry.size else None)
    return data.getvalue()


class SourceTests(unittest.TestCase):
    def test_safe_yaml_timestamp_and_ignored_fields(self):
        result = payload()
        self.assertEqual(result["source"]["revision"], SHA)
        timeline = result["conferences"][0]["editions"][0]["timeline"][0]
        self.assertEqual(timeline["deadline"], "2026-12-01 23:59:59")
        self.assertEqual(set(timeline), {"abstract_deadline", "deadline", "comment"})
        self.assertEqual(result, payload())

    def test_unknown_key_invalid_date_timezone_and_category_fail(self):
        for old, new in [
            (b"decision_deadline", b"surprise_deadline"),
            (b"AoE", b"CET"),
            (b"2026-12-01", b"2026-99-01"),
            (b"sub: AI", b"sub: SE"),
        ]:
            source = files()
            source["conference/AI/demo.yml"] = source["conference/AI/demo.yml"].replace(
                old, new
            )
            with self.subTest(new=new), self.assertRaises(ValueError):
                snapshot_from_files(source, SHA, "2026-11-03")

    def test_unsafe_yaml_is_rejected(self):
        source = files()
        source["conference/AI/demo.yml"] = (
            b"!!python/object/apply:os.system [echo nope]"
        )
        with self.assertRaises(yaml.YAMLError):
            snapshot_from_files(source, SHA, "2026-11-03")

    def test_archive_selection_and_unsafe_paths_links_size(self):
        self.assertEqual(conference_files(archive()), {"conference/AI/demo.yml": b"x"})
        self.assertEqual(conference_files(archive("repo/elsewhere/demo.yml")), {})
        for name, kind in [
            ("repo/../conference/AI/demo.yml", tarfile.REGTYPE),
            ("repo/conference/AI/demo.yml", tarfile.SYMTYPE),
        ]:
            with self.assertRaises(ValueError):
                conference_files(archive(name, kind))
        with (
            patch("app.integrations.conferences.client.MAX_YAML", 0),
            self.assertRaises(ValueError),
        ):
            conference_files(archive())

    def test_pax_metadata_counts_toward_expanded_size(self):
        data = io.BytesIO()
        with tarfile.open(
            fileobj=data, mode="w:gz", format=tarfile.PAX_FORMAT
        ) as archive_file:
            entry = tarfile.TarInfo("repo/ignored.txt")
            entry.size = 1
            entry.pax_headers = {"comment": "x" * 10000}
            archive_file.addfile(entry, io.BytesIO(b"x"))
        with patch("app.integrations.conferences.client.MAX_TAR", 2048):
            with self.assertRaisesRegex(ValueError, "expanded"):
                conference_files(data.getvalue())

    def test_replacement_shrink_and_missing_follow_fail(self):
        p = payload()
        old = copy.deepcopy(p)
        old["conferences"].append({**old["conferences"][0], "id": "ai-other"})
        with self.assertRaisesRegex(ValueError, "10%"):
            validate_replacement(p, old, set())
        with self.assertRaisesRegex(ValueError, "Followed"):
            validate_replacement(p, p, {"ai-gone"})

    def test_stale_is_additive_and_does_not_change_closed(self):
        p = snapshot(
            conference("ai-old", edition(2020, {"deadline": "2020-01-01 00:00:00"}))
        )
        catalog = catalog_from_snapshot(ConferenceSnapshotFile.model_validate(p))
        item = (
            ConferenceDeadlineService(lambda: catalog, lambda: NOW).deadlines().items[0]
        )
        self.assertEqual(item.status, "closed")
        self.assertTrue(item.needs_update)


class SyncTests(unittest.IsolatedAsyncioTestCase):
    def make(self, state=None):
        store = SimpleNamespace(
            state=AsyncMock(return_value=state),
            attempt=AsyncMock(),
            checked=AsyncMock(),
            followed_ids=AsyncMock(return_value=set()),
            save=AsyncMock(),
        )
        client = SimpleNamespace(
            latest=AsyncMock(return_value=(SHA, "2026-11-03")),
            download=AsyncMock(return_value=files()),
        )
        return ConferenceSync(store, client)

    async def test_unchanged_does_not_download_or_write_payload(self):
        job = self.make(
            SimpleNamespace(
                payload=payload(),
                snapshot_id=payload()["snapshot_id"],
                upstream_sha=SHA,
                checked_at=None,
                attempted_at=None,
            )
        )
        result = await job.sync(now=NOW)
        self.assertEqual(result["status"], "unchanged")
        job.client.download.assert_not_awaited()
        job.store.save.assert_not_awaited()
        job.store.checked.assert_awaited_once_with(NOW)

    async def test_changed_writes_only_after_validation_and_dry_run_does_not_write(
        self,
    ):
        for dry in (False, True):
            job = self.make()
            with patch(
                "app.services.conferences_sync.load_conference_catalog",
                return_value=catalog_from_snapshot(
                    ConferenceSnapshotFile.model_validate(payload())
                ),
            ):
                result = await job.sync(now=NOW, dry_run=dry)
            self.assertEqual(result["conferences"], 1)
            self.assertEqual(job.store.save.await_count, 0 if dry else 1)
            self.assertEqual(job.store.attempt.await_count, 0 if dry else 1)

    async def test_due_and_failure_backoff_survive_process_restart(self):
        for state, status in [
            (SimpleNamespace(checked_at=NOW, attempted_at=NOW), "not-due"),
            (SimpleNamespace(checked_at=None, attempted_at=NOW), "retry-delayed"),
        ]:
            job = self.make(state)
            self.assertEqual(
                (await job.sync(now=NOW + timedelta(minutes=30)))["status"], status
            )
            job.client.latest.assert_not_awaited()

    async def test_network_failure_preserves_old_payload(self):
        job = self.make()
        job.client.latest.side_effect = httpx.ReadTimeout("upstream")
        with self.assertRaises(httpx.ReadTimeout):
            await job.sync(now=NOW)
        job.store.save.assert_not_awaited()
        job.store.checked.assert_not_awaited()
        job.store.attempt.assert_awaited_once()

    async def test_protections_and_malformed_yaml_do_not_write(self):
        for invalid in ("shrink", "follow", "yaml"):
            job = self.make()
            previous = payload()
            if invalid == "shrink":
                previous["conferences"].append(
                    {**previous["conferences"][0], "id": "ai-other"}
                )
            if invalid == "follow":
                job.store.followed_ids.return_value = {"ai-gone"}
            if invalid == "yaml":
                job.client.download.return_value = {}
            with patch(
                "app.services.conferences_sync.load_conference_catalog",
                return_value=catalog_from_snapshot(
                    ConferenceSnapshotFile.model_validate(previous)
                ),
            ):
                with self.assertRaises(ValueError):
                    await job.sync(now=NOW)
            job.store.save.assert_not_awaited()

    async def test_github_transport_status_and_timeout(self):
        async def failing(request):
            raise httpx.ReadTimeout("slow", request=request)

        with self.assertRaises(httpx.ReadTimeout):
            await ConferenceGitHubClient(httpx.MockTransport(failing)).latest()
        with self.assertRaises(httpx.HTTPStatusError):
            await ConferenceGitHubClient(
                httpx.MockTransport(lambda r: httpx.Response(503))
            ).latest()


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_version_only_checks_and_refresh_singleflight(self):
        p = payload()
        clock = [0]
        store = SimpleNamespace(
            version=AsyncMock(return_value=p["snapshot_id"]),
            payload=AsyncMock(return_value=p),
        )
        cache = ConferenceCatalogCache(store, lambda: clock[0], ttl=300)
        with patch(
            "app.services.conferences_repository.chat_database_url",
            return_value="configured",
        ):
            catalogs = await asyncio.gather(*(cache.get() for _ in range(10)))
            first = catalogs[0]
            self.assertTrue(all(catalog is first for catalog in catalogs))
            store.payload.assert_awaited_once()
            clock[0] = 301
            self.assertIs(await cache.get(), first)
            store.payload.assert_awaited_once()
            p = copy.deepcopy(p)
            p["snapshot_id"] = "next"
            p["conferences"][0]["description"] = "Updated"
            store.version.return_value = "next"
            store.payload.return_value = p
            clock[0] = 602
            self.assertEqual((await cache.get()).snapshot.snapshot_id, "next")
            self.assertEqual(store.payload.await_count, 2)

    async def test_empty_db_and_failure_fallback_then_recovery(self):
        store = SimpleNamespace(
            version=AsyncMock(return_value=None), payload=AsyncMock()
        )
        cache = ConferenceCatalogCache(store, ttl=0)
        with patch(
            "app.services.conferences_repository.chat_database_url",
            return_value="configured",
        ):
            fallback = await cache.get()
            self.assertGreater(len(fallback.records), 300)
            store.version.side_effect = RuntimeError("offline")
            with self.assertLogs("app.services.conferences_repository", "ERROR"):
                self.assertIs(await cache.get(), fallback)
            store.version.side_effect = None
            store.version.return_value = payload()["snapshot_id"]
            store.payload.return_value = payload()
            good = await cache.get()
            self.assertEqual(len(good.records), 1)
            store.version.return_value = "broken"
            store.payload.return_value = {}
            with self.assertLogs("app.services.conferences_repository", "ERROR"):
                self.assertIs(await cache.get(), good)


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_conference_only_and_failure_isolated(self):
        from app.services.discovery_pool.scheduler import HomeFeedScheduler

        with patch.dict(
            os.environ,
            {"CONFERENCE_SYNC_ENABLED": "true", "HOME_FEED_SCHEDULER_ENABLED": "false"},
        ):
            with patch(
                "app.services.discovery_pool.scheduler.ConferenceSync.run",
                AsyncMock(return_value={"status": "updated"}),
            ):
                self.assertEqual(
                    await HomeFeedScheduler().run_due(NOW), ["conferences"]
                )
            with patch(
                "app.services.discovery_pool.scheduler.ConferenceSync.run",
                AsyncMock(side_effect=RuntimeError("failed")),
            ):
                with self.assertLogs("app.services.discovery_pool.scheduler", "ERROR"):
                    self.assertEqual(await HomeFeedScheduler().run_due(NOW), [])


class DailyBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_checks_before_24_hour_display_budget(self):
        state = SimpleNamespace(
            snapshot_id="test", upstream_sha=SHA, checked_at=NOW, attempted_at=NOW
        )
        store = SimpleNamespace(
            state=AsyncMock(return_value=state),
            attempt=AsyncMock(),
            checked=AsyncMock(),
        )
        client = SimpleNamespace(
            latest=AsyncMock(return_value=(SHA, "2026-11-03")), download=AsyncMock()
        )
        job = ConferenceSync(store, client)
        self.assertEqual(
            (await job.sync(now=NOW + timedelta(hours=22)))["status"], "not-due"
        )
        self.assertEqual(
            (await job.sync(now=NOW + timedelta(hours=23)))["status"], "unchanged"
        )
        client.download.assert_not_awaited()

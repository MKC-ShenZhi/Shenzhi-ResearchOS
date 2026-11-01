"""First-stage recommendation contracts without production data or a model."""

import asyncio
import os
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, update

from app.api import maintenance
from app.core.database import session_scope
from app.core.errors import BusinessError
from app.main import app
from app.models.interactions import PaperLikeRow
from app.models.reading_history import ReadingHistoryRow
from app.models.recommendation import BehaviorEventRow, RecommendationSnapshotRow, UserInterestProfileRow
from app.schemas.behavior import BehaviorBatchRequest, BehaviorEventInput
from app.schemas.discovery import DiscoveryPaper
from app.schemas.knowledge import PaperDetail, Provenance
from app.services.knowledge.service import KnowledgeServiceError
from app.services.library.collections import CollectionService
from app.services.library.paper_likes import PaperLikeService
from app.services.recommendation.behavior import BehaviorEventService
from app.services.recommendation.config import PROFILE_IMMEDIATE_EVENT_TYPES
from app.services.recommendation.evaluation import (
    compare_judged_baselines,
    engagement_summary,
    judged_quality,
    search_linkage_summary,
)
from app.services.recommendation.features import PaperFeatureService
from app.services.recommendation.maintenance import purge_expired
from app.services.recommendation.profile import (
    UserProfileService,
    _accumulate,
    _decay,
    _normalized,
)
from app.services.recommendation.recommendations import (
    Candidate,
    CandidateRecallService,
    RecommendationService,
    _blend,
    _rank,
)
from app.services.user.account_deletion import AccountDeletionService


def profile(**changes):
    result = {
        'algorithm_version': 'content-v1',
        'long_topics': {}, 'short_topics': {},
        'long_keywords': {}, 'short_keywords': {},
        'explicit_subjects': [], 'has_history': False,
    }
    result.update(changes)
    return result


def shared_list(*papers):
    async def daily_papers():
        return list(papers)
    return SimpleNamespace(daily_papers=daily_papers)


def curated(paper_id, title='Curated'):
    return DiscoveryPaper(id=paper_id, title=title, abstract='', year=2026,
                          thumbnail_url=f'/paper-thumbnails/{paper_id}.webp')


class BehaviorContractTests(unittest.TestCase):
    def test_rejects_spoofed_identity_and_explicit_events(self):
        with self.assertRaises(ValidationError):
            BehaviorEventInput.model_validate({
                'event_id': str(uuid4()), 'event_type': 'paper_like',
                'paper_id': 'paper:1', 'source': 'discovery',
            })
        with self.assertRaises(ValidationError):
            BehaviorEventInput.model_validate({
                'event_id': str(uuid4()), 'event_type': 'paper_click',
                'paper_id': 'paper:1', 'source': 'discovery', 'user_id': 'another-user',
            })

    def test_validates_recommendation_context_and_batch_size(self):
        event = {'event_id': str(uuid4()), 'event_type': 'recommendation_click',
                 'paper_id': 'paper:1', 'source': 'recommendation'}
        with self.assertRaises(ValidationError):
            BehaviorEventInput.model_validate(event)
        with self.assertRaises(ValidationError):
            BehaviorBatchRequest.model_validate({'events': [{
                'event_id': str(uuid4()), 'event_type': 'paper_click',
                'paper_id': 'paper:1', 'source': 'discovery',
            }] * 21})
        with self.assertRaises(ValidationError):
            BehaviorEventInput.model_validate({
                'event_id': str(uuid4()), 'event_type': 'active_read',
                'paper_id': 'paper:1', 'source': 'paper_detail', 'duration_seconds': 5,
            })
        self.assertEqual(BehaviorEventInput.model_validate({
            'event_id': str(uuid4()), 'event_type': 'search_submit',
            'query': 'retrieval augmented generation', 'source': 'search',
        }).query, 'retrieval augmented generation')
        self.assertEqual(BehaviorEventInput.model_validate({
            'event_id': str(uuid4()), 'event_type': 'abstract_expand',
            'paper_id': 'paper:1', 'source': 'search',
        }).event_type, 'abstract_expand')
        with self.assertRaises(ValidationError):
            BehaviorEventInput.model_validate({
                'event_id': str(uuid4()), 'event_type': 'paper_click',
                'paper_id': 'paper:1', 'source': 'discovery', 'query_id': str(uuid4()),
            })


    def test_attribution_ids_are_only_accepted_on_verified_recommendation_events(self):
        # A discovery or search event cannot carry a request_id that the
        # server would not verify against the caller's own snapshot.
        for event_type, source in [('paper_click', 'discovery'), ('search_result_click', 'search'),
                                   ('abstract_expand', 'recommendation')]:
            with self.assertRaises(ValidationError):
                BehaviorEventInput.model_validate({
                    'event_id': str(uuid4()), 'event_type': event_type,
                    'paper_id': 'paper:1', 'source': source, 'request_id': str(uuid4()),
                })
        with self.assertRaises(ValidationError):
            BehaviorEventInput.model_validate({
                'event_id': str(uuid4()), 'event_type': 'recommendation_click',
                'paper_id': 'paper:1', 'source': 'recommendation', 'request_id': 'not-a-uuid', 'rank': 1,
            })


class ProfileMathTests(unittest.TestCase):
    def test_weak_navigation_and_impression_events_wait_for_ttl_refresh(self):
        self.assertTrue({'paper_like', 'paper_unlike', 'paper_collect', 'topic_follow',
                         'paper_read', 'active_read', 'search_submit'}.issubset(
                             PROFILE_IMMEDIATE_EVENT_TYPES,
                         ))
        self.assertTrue({'paper_click', 'paper_detail_view', 'abstract_expand',
                         'recommendation_click', 'recommendation_impression',
                         'paper_impression', 'search_result_click'}.isdisjoint(
                             PROFILE_IMMEDIATE_EVENT_TYPES,
                         ))

    def test_engagement_and_judged_quality_are_aggregate_only(self):
        common = {'user_id': 'user-a', 'request_id': 'request-a', 'entity_id': 'paper:1', 'rank': 1}
        events = [SimpleNamespace(**common, event_type=kind) for kind in (
            'recommendation_impression', 'recommendation_impression', 'recommendation_click',
        )]
        events.append(SimpleNamespace(**{**common, 'entity_id': 'paper:2'}, event_type='recommendation_click'))
        result = engagement_summary(events)
        self.assertEqual(result['unique_impressions'], 1)
        self.assertEqual(result['clicks_with_impression'], 1)
        self.assertEqual(result['clicks_without_impression'], 1)
        self.assertEqual(result['repeated_impression_events'], 1)
        self.assertEqual(result['click_through_rate'], 1.0)
        self.assertEqual(judged_quality(['paper:1', 'paper:2'], {'paper:2'}, 1), {
            'recall_at_k': 0.0, 'ndcg_at_k': 0.0,
        })
        self.assertEqual(judged_quality(['paper:2', 'paper:1'], {'paper:2'}, 1), {
            'recall_at_k': 1.0, 'ndcg_at_k': 1.0,
        })
        self.assertIsNone(judged_quality(['paper:1'], set(), 1)['ndcg_at_k'])

    def test_compares_baselines_on_identical_candidate_sets(self):
        result = compare_judged_baselines({
            'cases': [{
                'relevant_ids': ['paper:2'],
                'rankings': {
                    'global_discovery': ['paper:1', 'paper:2'],
                    'explicit_topic': ['paper:2', 'paper:1'],
                    'content_v1': ['paper:2', 'paper:1'],
                },
            }],
        }, [1, 2])
        self.assertEqual(result['evaluated_cases'], 1)
        self.assertEqual(result['metrics']['global_discovery']['@1'], {
            'recall': 0.0, 'ndcg': 0.0,
        })
        self.assertEqual(result['metrics']['content_v1']['@1'], {
            'recall': 1.0, 'ndcg': 1.0,
        })

    def test_search_linkage_summary_is_aggregate_and_user_scoped(self):
        events = [
            SimpleNamespace(user_id='user-a', query_id='query-a', event_type='search_submit'),
            SimpleNamespace(user_id='user-a', query_id='query-a', event_type='search_result_click'),
            SimpleNamespace(user_id='user-a', query_id='query-missing', event_type='search_result_click'),
            SimpleNamespace(user_id='user-b', query_id='query-a', event_type='search_result_click'),
            SimpleNamespace(user_id='user-a', query_id=None, event_type='search_result_click'),
        ]
        self.assertEqual(search_linkage_summary(events), {
            'search_result_clicks': 4,
            'clicks_with_matching_search_submit': 1,
            'clicks_without_query_id': 1,
            'clicks_with_unmatched_query_id': 2,
        })

    def test_rejects_unmatched_candidate_sets_and_relevance_labels(self):
        with self.assertRaisesRegex(ValueError, 'same candidate set'):
            compare_judged_baselines({'cases': [{
                'relevant_ids': ['p1'],
                'rankings': {'global': ['p1', 'p2'], 'content': ['p1', 'p3']},
            }]}, [5])
        with self.assertRaisesRegex(ValueError, 'outside the candidate set'):
            compare_judged_baselines({'cases': [{
                'relevant_ids': ['p3'],
                'rankings': {'global': ['p1', 'p2'], 'content': ['p2', 'p1']},
            }]}, [5])

    def test_decay_and_long_short_profiles(self):
        now = datetime(2026, 10, 25, tzinfo=UTC)
        self.assertAlmostEqual(_decay('paper_like', now - timedelta(days=45), now), 0.5)
        long_scores, short_scores = {}, {}
        from collections import defaultdict
        long_scores, short_scores = defaultdict(float), defaultdict(float)
        _accumulate(['RAG', 'rag'], 2, now - timedelta(days=20), 'paper_like',
                    now, long_scores, short_scores)
        self.assertGreater(long_scores['rag'], 0)
        self.assertEqual(short_scores['rag'], 0)
        self.assertEqual(_normalized({}), {})
        self.assertEqual(_normalized({'rag': 2, 'vision': 1}), {'rag': 1.0, 'vision': 0.5})

    def test_rank_reasons_require_actual_features(self):
        paper = {'id': 'p1', 'title': 'P', 'abstract': '', 'authors': [], 'year': 2026,
                 'venue': None, 'pdf_url': None, 'thumbnail_url': None}
        matching = Candidate(paper, ['RAG'], ['retrieval'], {'followed_topic'})
        p = profile(long_topics={'rag': 1}, explicit_subjects=['RAG'], has_history=True)
        score, reason = _rank(matching, p, None, 2026)
        self.assertGreater(score, 0.5)
        self.assertIn('关注的主题', reason)
        unrelated = Candidate(paper, [], [], {'keyword'})
        low, reason = _rank(unrelated, p, None, 2026)
        self.assertLessEqual(low, 0.15)
        # No real signal: the card shows no reason rather than a generic label.
        self.assertIsNone(reason)
        self.assertEqual(_rank(unrelated, p, 0.5, 2026)[1], '近期受到平台用户关注')

    def test_blend_interleaves_two_personal_picks_per_shared_paper_without_repeats(self):
        personal = [{'id': f'p{index}'} for index in range(5)] + [{'id': 's1'}]
        shared = [{'id': 's0'}, {'id': 's1'}, {'id': 'p0'}, {'id': 's2'}, {'id': 's3'}]
        self.assertEqual([item['id'] for item in _blend(personal, shared)],
                         ['p0', 'p1', 's0', 'p2', 'p3', 's1', 'p4', 's2', 's3'])
        self.assertEqual([item['id'] for item in _blend([], shared[:2])], ['s0', 's1'])
        self.assertEqual(_blend([], []), [])


class RecallTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_paper_history_skips_metadata_lookup(self):
        knowledge = SimpleNamespace(get_paper=AsyncMock())
        self.assertEqual(await PaperFeatureService(knowledge).get_many([]), {})
        knowledge.get_paper.assert_not_awaited()

    async def test_deduplicates_sources_and_survives_partial_failure(self):
        paper = SimpleNamespace(id='paper:1', title='One', abstract=None,
                                authors=[], year=2026, venue=None,
                                subjects=['RAG'], keywords=['retrieval'],
                                image_id='/images/2026/paper-1.webp')
        knowledge = SimpleNamespace(
            search_by_subject=AsyncMock(side_effect=[
                SimpleNamespace(results=[paper]), KnowledgeServiceError('unavailable'),
            ]),
            search=AsyncMock(return_value=SimpleNamespace(results=[paper])),
        )
        result = await CandidateRecallService(knowledge).recall(profile(
            explicit_subjects=['RAG', 'vision'], long_keywords={'retrieval': 1},
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].paper['id'], 'paper:1')
        self.assertEqual(result[0].paper['image_id'], '/images/2026/paper-1.webp')
        self.assertEqual((result[0].paper['keywords'], result[0].paper['subjects']), (['retrieval'], ['RAG']))
        self.assertEqual(result[0].sources, {'followed_topic', 'keyword'})

    async def test_all_knowledge_failures_leave_no_personal_candidates(self):
        knowledge = SimpleNamespace(search_by_subject=AsyncMock(side_effect=KnowledgeServiceError('down')),
                                    search=AsyncMock(side_effect=KnowledgeServiceError('down')))
        result = await CandidateRecallService(knowledge).recall(profile(
            long_topics={'rag': 1}, long_keywords={'retrieval': 1},
        ))
        # The shared daily list is blended in by RecommendationService, not recall.
        self.assertEqual(result, [])

    async def test_keyword_retrieval_is_a_scored_search_interest_signal(self):
        paper = SimpleNamespace(id='paper:graph', title='Graph paper', abstract=None,
                                authors=[], year=2026, venue=None,
                                subjects=[], keywords=['networks'], image_id=None)
        knowledge = SimpleNamespace(
            search=AsyncMock(return_value=SimpleNamespace(results=[paper])),
            search_by_subject=AsyncMock(),
        )
        interests = profile(short_keywords={'graph neural network': 1}, has_history=True)
        candidates = await CandidateRecallService(knowledge).recall(interests)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].keyword_recall_match, 0.4)
        score, reason = _rank(candidates[0], interests, None, 2026)
        self.assertGreater(score, 0.15)
        self.assertEqual(reason, '与你近期搜索的方向相关')

    async def test_unexpected_source_errors_and_timeouts_are_isolated(self):
        paper = SimpleNamespace(id='paper:ok', title='Survivor', abstract=None,
                                authors=[], year=2026, venue=None,
                                subjects=['RAG'], keywords=[], image_id=None)

        async def never_returns(*_args, **_kwargs):
            await asyncio.sleep(60)

        knowledge = SimpleNamespace(
            search_by_subject=AsyncMock(side_effect=[
                RuntimeError('contract drift'), SimpleNamespace(results=[paper]),
            ]),
            search=never_returns,
        )

        with patch('app.services.recommendation.config.RECALL_TIMEOUT_SECONDS', 0.05), \
                self.assertLogs('app.services.recommendation.recommendations', 'WARNING') as logs:
            result = await CandidateRecallService(knowledge).recall(profile(
                explicit_subjects=['private subject a', 'RAG'], long_keywords={'secret query': 1},
            ))
        self.assertEqual([item.paper['id'] for item in result], ['paper:ok'])
        # Recall values may be private search text; logs carry only error types.
        self.assertFalse(any('secret query' in line or 'private subject' in line for line in logs.output))

    async def test_recall_limits_queries_and_merges_duplicate_ids_across_sources(self):
        paper = SimpleNamespace(id='shared', title='Shared', abstract=None,
                                authors=[], year=2026, venue=None,
                                subjects=['RAG'], keywords=['retrieval'], image_id=None)
        knowledge = SimpleNamespace(
            search_by_subject=AsyncMock(return_value=SimpleNamespace(results=[paper, paper])),
            search=AsyncMock(return_value=SimpleNamespace(results=[paper])),
        )
        result = await CandidateRecallService(knowledge).recall(profile(
            explicit_subjects=['a', 'b', 'c', 'd', 'e'], long_topics={'f': 1}, long_keywords={'g': 1},
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].sources, {'followed_topic', 'inferred_topic', 'keyword'})
        calls = knowledge.search_by_subject.await_count + knowledge.search.await_count
        self.assertEqual(calls, 4)

    async def test_home_year_bounds_keyword_search_and_filters_overfetched_subjects(self):
        def paper(paper_id, year):
            return SimpleNamespace(id=paper_id, title=paper_id, abstract=None, authors=[], year=year,
                                   venue=None, subjects=['RAG'], keywords=[], image_id='/images/p.png')
        knowledge = SimpleNamespace(
            search=AsyncMock(return_value=SimpleNamespace(results=[paper('keyword:2026', 2026)])),
            search_by_subject=AsyncMock(return_value=SimpleNamespace(results=[
                paper('subject:2024', 2024), paper('subject:2026', 2026),
            ])),
        )
        result = await CandidateRecallService(knowledge).recall(
            profile(explicit_subjects=['RAG'], long_keywords={'retrieval': 1}), year=2026,
        )
        self.assertEqual({item.paper['id'] for item in result}, {'keyword:2026', 'subject:2026'})
        request = knowledge.search.await_args.args[0]
        self.assertEqual((request.year_from, request.year_to), (2026, 2026))
        knowledge.search_by_subject.assert_awaited_once_with('RAG', limit=36)

    async def test_metadata_failures_never_fail_or_invent_profile_features(self):
        detail = PaperDetail(id='paper:ok', title='OK', subjects=['RAG'], keywords=[],
                             provenance=Provenance(external_id='paper:ok'))

        async def get_paper(paper_id):
            if paper_id == 'paper:broken':
                raise ValueError('unexpected payload')
            if paper_id == 'paper:slow':
                await asyncio.sleep(60)
            return detail

        with patch('app.services.recommendation.config.METADATA_TIMEOUT_SECONDS', 0.05):
            result = await PaperFeatureService(SimpleNamespace(get_paper=get_paper)).get_many(
                ['paper:ok', 'paper:broken', 'paper:slow', 'paper:ok'],
            )
        self.assertEqual(list(result), ['paper:ok'])

    def test_diversity_never_promotes_distant_candidate(self):
        def item(index, subject, score):
            return (score, Candidate({'id': str(index)}, [subject], [], set()), 'reason')
        ranked = [item(i, 'rag', 1 - i * 0.01) for i in range(5)]
        ranked += [item(6, 'vision', 0.3)]
        result = RecommendationService._diversify(ranked)
        self.assertEqual([entry[1].paper['id'] for entry in result], ['0', '1', '2', '3', '4', '6'])


class RecommendationApiAuthTests(unittest.TestCase):
    def test_anonymous_cannot_read_profile_or_recommendations(self):
        with patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'}):
            client = TestClient(app)
            headers = {'x-shenzhi-bff-secret': 'test-secret',
                       'x-shenzhi-anonymous-id': str(uuid4())}
            self.assertEqual(client.get('/api/v1/recommendations/me/profile', headers=headers).status_code, 401)
            self.assertEqual(client.get('/api/v1/recommendations/papers', headers=headers).status_code, 401)
            self.assertEqual(client.post('/api/v1/behavior-events/batch', headers=headers,
                                         json={'events': []}).status_code, 401)

    def test_authenticated_routes_bind_the_trusted_bff_user(self):
        headers = {'x-shenzhi-bff-secret': 'test-secret', 'x-shenzhi-user-id': 'trusted-user'}
        with patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'}):
            with patch('app.api.recommendations.service.page', new_callable=AsyncMock) as page:
                page.return_value = {'items': [], 'next_cursor': None, 'has_more': False,
                                     'request_id': str(uuid4()), 'total': 0,
                                     'algorithm_version': 'content-v1'}
                response = TestClient(app).get('/api/v1/recommendations/papers?limit=3', headers=headers)
                self.assertEqual(response.status_code, 200)
                page.assert_awaited_once_with('trusted-user', limit=3, cursor=None)
            with patch('app.api.behavior.service.record_batch', new_callable=AsyncMock) as record:
                record.return_value = 1
                event = {'event_id': str(uuid4()), 'event_type': 'paper_click',
                         'paper_id': 'paper:1', 'source': 'search'}
                response = TestClient(app).post('/api/v1/behavior-events/batch', headers=headers,
                                                json={'events': [event]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(record.await_args.args[0], 'trusted-user')

    def test_scheduled_maintenance_requires_cron_secret(self):
        client = TestClient(app)
        path = '/api/v1/internal/recommendation-maintenance'
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(client.get(path).status_code, 503)
        with patch.dict(os.environ, {'CRON_SECRET': 'test-cron-secret'}):
            self.assertEqual(client.get(path, headers={'authorization': 'Bearer wrong'}).status_code, 401)
            with patch.object(maintenance, 'purge_expired', new_callable=AsyncMock) as purge:
                purge.return_value = (3, 2)
                response = client.get(path, headers={
                    'authorization': 'Bearer test-cron-secret',
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['data'], {
                'deleted_events': 3,
                'deleted_recommendation_snapshots': 2,
            })


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class RecommendationPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        self.user_id = f'recommendation-test-{uuid4()}'
        self.other_id = f'recommendation-other-{uuid4()}'
        self.paper_id = f'paper:recommendation:{uuid4()}'

    async def asyncTearDown(self):
        await AccountDeletionService().delete_all_for_user(self.user_id)
        await AccountDeletionService().delete_all_for_user(self.other_id)
        from app.core.database import dispose_engine
        await dispose_engine()

    async def test_batch_idempotence_and_relationship_events(self):
        event_id = uuid4()
        batch = BehaviorBatchRequest.model_validate({'events': [{
            'event_id': str(event_id), 'event_type': 'paper_click',
            'paper_id': self.paper_id, 'source': 'discovery',
        }]})
        behavior = BehaviorEventService()
        self.assertEqual(await behavior.record_batch(self.user_id, batch), 1)
        self.assertEqual(await behavior.record_batch(self.user_id, batch), 0)
        likes = PaperLikeService()
        await likes.like(self.user_id, self.paper_id)
        await likes.like(self.user_id, self.paper_id)
        await likes.unlike(self.user_id, self.paper_id)
        folders = (await CollectionService().folders(self.user_id)).folders
        collections = CollectionService()
        await collections.update_paper_folders(self.user_id, self.paper_id, [folders[0].id])
        await collections.update_paper_folders(self.user_id, self.paper_id, [folders[0].id, folders[1].id])
        await collections.remove_paper(self.user_id, folders[0].id, self.paper_id)
        await collections.remove_paper(self.user_id, folders[1].id, self.paper_id)
        async with session_scope() as session:
            types = list(await session.scalars(select(BehaviorEventRow.event_type).where(
                BehaviorEventRow.user_id == self.user_id,
            )))
            others = await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.other_id,
            ))
        self.assertEqual(sorted(types), sorted([
            'paper_click', 'paper_like', 'paper_unlike', 'paper_collect', 'paper_uncollect',
        ]))
        self.assertEqual(others, 0)

    async def test_concurrent_batches_respect_the_per_user_limit(self):
        behavior = BehaviorEventService()
        batches = [BehaviorBatchRequest.model_validate({'events': [{
            'event_id': str(uuid4()), 'event_type': 'paper_click',
            'paper_id': self.paper_id, 'source': 'discovery',
        } for _ in range(20)]}) for _ in range(7)]
        results = await asyncio.gather(
            *(behavior.record_batch(self.user_id, batch) for batch in batches),
            return_exceptions=True,
        )
        self.assertEqual(sum(result for result in results if isinstance(result, int)), 120)
        self.assertEqual(sum(isinstance(result, Exception) for result in results), 1)
        async with session_scope() as session:
            count = await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.user_id,
            ))
        self.assertEqual(count, 120)

    async def test_profile_rebuild_and_private_snapshot_cursor(self):
        await PaperLikeService().like(self.user_id, self.paper_id)
        paper = PaperDetail(
            id=self.paper_id, title='RAG study', subjects=['RAG'],
            keywords=['retrieval'], provenance=Provenance(external_id=self.paper_id),
        )
        features = SimpleNamespace(get_many=AsyncMock(return_value={self.paper_id: paper}))
        profiles = UserProfileService(features=features)
        built = await profiles.rebuild(self.user_id)
        self.assertEqual(built['long_topics']['rag'], 1)
        self.assertEqual(built['long_keywords']['retrieval'], 1)
        await PaperLikeService().unlike(self.user_id, self.paper_id)
        cleared = await profiles.rebuild(self.user_id)
        self.assertEqual(cleared['long_topics'], {})

        service = self._service_with([curated(f'{self.paper_id}:{index}') for index in (1, 2)])
        first = await service.page(self.user_id, limit=1)
        self.assertEqual(len(first['items']), 1)
        second = await service.page(self.user_id, limit=1, cursor=first['next_cursor'])
        self.assertNotEqual(first['items'][0]['id'], second['items'][0]['id'])
        with self.assertRaises(BusinessError):
            await service.page(self.other_id, limit=1, cursor=first['next_cursor'])
        feedback = BehaviorBatchRequest.model_validate({'events': [{
            'event_id': str(uuid4()), 'event_type': 'recommendation_click',
            'paper_id': first['items'][0]['id'], 'source': 'recommendation',
            'request_id': first['request_id'], 'rank': first['items'][0]['rank'],
        }]})
        self.assertEqual(await BehaviorEventService().record_batch(self.user_id, feedback), 1)
        with self.assertRaises(BusinessError):
            await BehaviorEventService().record_batch(self.other_id, feedback)

    async def test_profile_debounces_weak_events_and_refreshes_strong_state(self):
        paper = PaperDetail(
            id=self.paper_id, title='RAG study', subjects=['RAG'],
            keywords=['retrieval'], provenance=Provenance(external_id=self.paper_id),
        )
        features = SimpleNamespace(get_many=AsyncMock(return_value={self.paper_id: paper}))
        profiles = UserProfileService(features=features)
        initial = await profiles.get(self.user_id)
        features.get_many.reset_mock()

        weak_click = BehaviorBatchRequest.model_validate({'events': [{
            'event_id': str(uuid4()), 'event_type': 'paper_click',
            'paper_id': self.paper_id, 'source': 'discovery',
        }]})
        await BehaviorEventService().record_batch(self.user_id, weak_click)
        cached = await profiles.get(self.user_id)
        self.assertEqual(cached['computed_at'], initial['computed_at'])
        features.get_many.assert_not_awaited()

        await PaperLikeService().like(self.user_id, self.paper_id)
        refreshed = await profiles.get(self.user_id)
        self.assertIn('rag', refreshed['long_topics'])
        features.get_many.assert_awaited_once_with([self.paper_id])

    async def test_search_only_interest_changes_recommendation_order(self):
        query_id = uuid4()
        batch = BehaviorBatchRequest.model_validate({'events': [{
            'event_id': str(query_id), 'event_type': 'search_submit',
            'query_id': str(query_id), 'query': 'RAG', 'source': 'search',
        }]})
        await BehaviorEventService().record_batch(self.user_id, batch)
        click = BehaviorBatchRequest.model_validate({'events': [{
            'event_id': str(uuid4()), 'event_type': 'search_result_click',
            'query_id': str(query_id), 'paper_id': self.paper_id, 'source': 'search', 'rank': 1,
        }]})
        await BehaviorEventService().record_batch(self.user_id, click)
        async with session_scope() as session:
            linked = list(await session.scalars(select(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.user_id,
                BehaviorEventRow.query_id == query_id,
            )))
        self.assertEqual({event.event_type for event in linked}, {'search_submit', 'search_result_click'})
        profiles = UserProfileService(features=SimpleNamespace(get_many=AsyncMock(return_value={})))
        built = await profiles.rebuild(self.user_id)
        self.assertTrue(built['has_history'])
        self.assertEqual(built['short_keywords'], {'rag': 1.0})
        self.assertEqual(built['long_keywords'], {})
        def candidate(paper_id: str, keyword: str) -> Candidate:
            return Candidate({
                'id': paper_id, 'title': paper_id, 'abstract': '', 'authors': [],
                'year': 2026, 'venue': None, 'pdf_url': None, 'thumbnail_url': None,
                'image_id': f'/images/2026/{paper_id.replace(":", "-")}.webp',
            }, [], [keyword], {'keyword'})
        unrelated = candidate('paper:a-unrelated', 'vision')
        matching = candidate('paper:z-matching', 'RAG')
        service = self._service_with([], interests=built, candidates=[unrelated, matching])
        page = await service.page(self.user_id, limit=2)
        self.assertEqual([item['id'] for item in page['items']], ['paper:z-matching', 'paper:a-unrelated'])
        self.assertEqual(page['items'][0]['reason'], '与你关注的论文关键词相关')

    async def test_concurrent_detail_views_emit_one_debounced_event(self):
        from app.services.library.reading_history import ReadingHistoryService

        service = ReadingHistoryService()
        await asyncio.gather(*(service.record(self.user_id, self.paper_id) for _ in range(12)))
        async with session_scope() as session:
            count = await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.user_id,
                BehaviorEventRow.entity_id == self.paper_id,
                BehaviorEventRow.event_type == 'paper_detail_view',
            ))
        self.assertEqual(count, 1)

    async def test_detail_view_debounce_uses_persisted_ten_minute_window(self):
        from app.services.library.reading_history import ReadingHistoryService

        service = ReadingHistoryService()
        await service.record(self.user_id, self.paper_id)
        await service.record(self.user_id, self.paper_id)
        async with session_scope() as session:
            count = await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.user_id,
                BehaviorEventRow.entity_id == self.paper_id,
                BehaviorEventRow.event_type == 'paper_detail_view',
            ))
        self.assertEqual(count, 1)

        async with session_scope() as session:
            await session.execute(update(ReadingHistoryRow).where(
                ReadingHistoryRow.user_id == self.user_id,
                ReadingHistoryRow.paper_id == self.paper_id,
            ).values(last_viewed_at=datetime.now(UTC) - timedelta(minutes=11)))
        await service.record(self.user_id, self.paper_id)
        async with session_scope() as session:
            count = await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.user_id,
                BehaviorEventRow.entity_id == self.paper_id,
                BehaviorEventRow.event_type == 'paper_detail_view',
            ))
        self.assertEqual(count, 2)

    async def test_event_retention_keeps_active_explicit_interest_rebuildable(self):
        now = datetime(2026, 10, 25, tzinfo=UTC)
        old = now - timedelta(days=91)
        await PaperLikeService().like(self.user_id, self.paper_id)
        async with session_scope() as session:
            await session.execute(update(PaperLikeRow).where(
                PaperLikeRow.user_id == self.user_id,
                PaperLikeRow.paper_id == self.paper_id,
            ).values(created_at=old))
            await session.execute(update(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.user_id,
                BehaviorEventRow.entity_id == self.paper_id,
                BehaviorEventRow.event_type == 'paper_like',
            ).values(occurred_at=old, received_at=old))

        self.assertEqual(await purge_expired(now), (1, 0))
        paper = PaperDetail(
            id=self.paper_id, title='Older liked paper', subjects=['RAG'],
            keywords=['retrieval'], provenance=Provenance(external_id=self.paper_id),
        )
        rebuilt = await UserProfileService(
            features=SimpleNamespace(get_many=AsyncMock(return_value={self.paper_id: paper})),
        ).rebuild(self.user_id)
        self.assertGreater(rebuilt['long_topics']['rag'], 0)
        self.assertGreater(rebuilt['long_keywords']['retrieval'], 0)

    async def test_distinct_interests_weights_rebuild_and_user_isolation(self):
        collected_id = f'paper:collected:{uuid4()}'
        await PaperLikeService().like(self.user_id, self.paper_id)
        folders = (await CollectionService().folders(self.user_id)).folders
        await CollectionService().update_paper_folders(self.user_id, collected_id, [folders[0].id])
        papers = {
            self.paper_id: PaperDetail(
                id=self.paper_id, title='Vision study', subjects=['Vision'], keywords=[],
                provenance=Provenance(external_id=self.paper_id),
            ),
            collected_id: PaperDetail(
                id=collected_id, title='RAG study', subjects=['RAG'], keywords=[],
                provenance=Provenance(external_id=collected_id),
            ),
        }
        profiles = UserProfileService(features=SimpleNamespace(get_many=AsyncMock(return_value=papers)))
        first = await profiles.rebuild(self.user_id)
        self.assertEqual(first['long_topics'], {'vision': 0.5, 'rag': 1.0})
        self.assertEqual((await profiles.rebuild(self.user_id))['long_topics'], first['long_topics'])
        self.assertEqual((await profiles.rebuild(self.other_id))['long_topics'], {})
        await CollectionService().remove_paper(self.user_id, folders[0].id, collected_id)
        self.assertEqual((await profiles.rebuild(self.user_id))['long_topics'], {'vision': 1.0})

    async def test_retention_purges_old_events_and_expired_snapshots(self):
        now = datetime(2026, 10, 25, tzinfo=UTC)
        async with session_scope() as session:
            session.add(BehaviorEventRow(
                event_id=uuid4(), user_id=self.user_id, event_type='paper_click',
                entity_type='paper', entity_id=self.paper_id, source='discovery',
                occurred_at=now - timedelta(days=91), received_at=now - timedelta(days=91),
            ))
            session.add(BehaviorEventRow(
                event_id=uuid4(), user_id=self.user_id, event_type='paper_click',
                entity_type='paper', entity_id=self.paper_id, source='discovery',
                occurred_at=now, received_at=now,
            ))
            session.add(RecommendationSnapshotRow(
                request_id=uuid4(), user_id=self.user_id, algorithm_version='content-v1',
                created_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1), items=[],
            ))
        self.assertEqual(await purge_expired(now), (1, 1))
        async with session_scope() as session:
            remaining = await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.user_id,
            ))
        self.assertEqual(remaining, 1)

    def _service_with(self, shared, interests=None, candidates=()):
        return RecommendationService(
            profiles=SimpleNamespace(get=AsyncMock(return_value=interests or profile())),
            recall=SimpleNamespace(recall=AsyncMock(return_value=list(candidates))),
            discovery=shared_list(*shared),
        )

    def _candidates(self, count):
        return [curated(f'{self.paper_id}:{index}', f'Paper {index}') for index in range(count)]

    async def test_personal_picks_blend_with_the_complete_shared_list(self):
        def recalled(paper_id, image_id):
            return Candidate({
                'id': paper_id, 'title': paper_id, 'abstract': '', 'authors': [], 'year': 2026,
                'venue': None, 'pdf_url': None, 'thumbnail_url': None, 'image_id': image_id,
            }, ['RAG'], [], {'followed_topic'})
        interests = profile(explicit_subjects=['RAG'], long_topics={'rag': 1}, has_history=True)
        liked = f'{self.paper_id}:liked'
        await PaperLikeService().like(self.user_id, liked)
        shared = [curated(f'{self.paper_id}:shared:{index}') for index in range(4)] + [curated(liked)]
        candidates = [
            recalled(f'{self.paper_id}:with-image', '/images/2026/with-image.webp'),
            recalled(f'{self.paper_id}:no-image', None),
            # SVG is never served by the web image proxy, so it counts as no image.
            recalled(f'{self.paper_id}:svg', '/images/ICLR_2026/x.svg'),
            # Recalled by search but also curated: keeps the static thumbnail.
            recalled(shared[3].id, None),
            recalled(liked, '/images/2026/liked.webp'),
        ]
        service = self._service_with(shared, interests, candidates)
        page = await service.page(self.user_id, limit=48)
        # Recall is bounded to the year the shared home list shows.
        self.assertEqual(service.recall.recall.await_args.kwargs, {'year': 2026})
        items = page['items']
        ids = [item['id'] for item in items]
        self.assertNotIn(f'{self.paper_id}:no-image', ids)
        self.assertNotIn(f'{self.paper_id}:svg', ids)
        self.assertNotIn(liked, ids)
        self.assertEqual(len(ids), len(set(ids)))
        # Two personal picks, then the shared list continues in its daily order.
        self.assertEqual(sorted(ids[:2]), sorted([f'{self.paper_id}:with-image', shared[3].id]))
        self.assertEqual(ids[2:], [paper.id for paper in shared[:3]])
        by_id = {item['id']: item for item in items}
        self.assertEqual(by_id[shared[3].id]['thumbnail_url'], shared[3].thumbnail_url)
        self.assertEqual(by_id[f'{self.paper_id}:with-image']['reason'], '与你关注的主题相匹配')
        self.assertIsNone(by_id[shared[0].id]['reason'])
        self.assertEqual(by_id[shared[0].id]['sources'], ['global_discovery'])
        self.assertEqual([item['rank'] for item in items], list(range(1, len(items) + 1)))

    async def test_personal_picks_are_capped_and_the_shared_list_is_never_truncated(self):
        candidates = [Candidate({
            'id': f'{self.paper_id}:personal:{index:03d}', 'title': 'P', 'abstract': '', 'authors': [],
            'year': 2026, 'venue': None, 'pdf_url': None, 'thumbnail_url': None,
            'image_id': f'/images/2026/{index}.webp',
        }, ['RAG'], [], {'followed_topic'}) for index in range(130)]
        shared = self._candidates(300)
        page = await self._service_with(
            shared, profile(explicit_subjects=['RAG'], has_history=True), candidates,
        ).page(self.user_id, limit=1)
        self.assertEqual(page['total'], 100 + 300)

    async def test_shared_list_failure_keeps_personal_picks(self):
        def broken():
            raise ValueError('snapshot schema drift')
        candidate = Candidate({
            'id': f'{self.paper_id}:personal', 'title': 'P', 'abstract': '', 'authors': [], 'year': 2026,
            'venue': None, 'pdf_url': None, 'thumbnail_url': None, 'image_id': '/images/2026/p.webp',
        }, ['RAG'], [], {'followed_topic'})
        service = self._service_with([], profile(explicit_subjects=['RAG']), [candidate])
        service.discovery = SimpleNamespace(daily_papers=broken)
        with self.assertLogs('app.services.recommendation.recommendations', 'WARNING'):
            page = await service.page(self.user_id, limit=12)
        self.assertEqual([item['id'] for item in page['items']], [candidate.paper['id']])

    async def test_snapshot_cursor_traverses_without_duplicates_or_loss(self):
        service = self._service_with(self._candidates(29))
        first = await service.page(self.user_id, limit=12)
        pages, cursor = [first], first['next_cursor']
        while cursor:
            again = await service.page(self.user_id, limit=12, cursor=cursor)
            # Re-reading one cursor (a retried request) returns the same slice.
            self.assertEqual(again, await service.page(self.user_id, limit=12, cursor=cursor))
            pages.append(again)
            cursor = again['next_cursor']
        ids = [item['id'] for page in pages for item in page['items']]
        ranks = [item['rank'] for page in pages for item in page['items']]
        self.assertEqual(len(ids), 29)
        self.assertEqual(len(set(ids)), 29)
        self.assertEqual(ranks, list(range(1, 30)))
        self.assertEqual({page['request_id'] for page in pages}, {first['request_id']})
        self.assertFalse(pages[-1]['has_more'])
        # Recall ran once: later pages never re-rank or mix another snapshot.
        service.recall.recall.assert_awaited_once()

    async def test_stale_foreign_and_malformed_cursors(self):
        service = self._service_with(self._candidates(3))
        first = await service.page(self.user_id, limit=1)
        for user in (self.other_id,):
            with self.assertRaises(BusinessError) as foreign:
                await service.page(user, limit=1, cursor=first['next_cursor'])
            self.assertEqual(foreign.exception.status, 409)
        with self.assertRaises(BusinessError) as missing:
            await service.page(self.user_id, limit=1, cursor=f'{uuid4()}:1')
        self.assertEqual(missing.exception.status, 409)
        for malformed in ('nope', f'{first["request_id"]}:x', f'{first["request_id"]}:99'):
            with self.assertRaises(BusinessError) as invalid:
                await service.page(self.user_id, limit=1, cursor=malformed)
            self.assertEqual(invalid.exception.status, 400)
        async with session_scope() as session:
            await session.execute(update(RecommendationSnapshotRow).where(
                RecommendationSnapshotRow.request_id == UUID(first['request_id']),
            ).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        with self.assertRaises(BusinessError) as expired:
            await service.page(self.user_id, limit=1, cursor=first['next_cursor'])
        self.assertEqual(expired.exception.status, 409)
        # Feedback against the expired request is rejected, not attributed.
        with self.assertRaises(BusinessError):
            await BehaviorEventService().record_batch(self.user_id, BehaviorBatchRequest.model_validate({'events': [{
                'event_id': str(uuid4()), 'event_type': 'recommendation_click',
                'paper_id': first['items'][0]['id'], 'source': 'recommendation',
                'request_id': first['request_id'], 'rank': 1,
            }]}))

    async def test_feedback_must_match_the_snapshot_item_and_rank(self):
        service = self._service_with(self._candidates(2))
        first = await service.page(self.user_id, limit=2)
        for paper_id, rank in [(first['items'][0]['id'], 2), ('paper:not-recommended', 1)]:
            with self.assertRaises(BusinessError):
                await BehaviorEventService().record_batch(self.user_id, BehaviorBatchRequest.model_validate({'events': [{
                    'event_id': str(uuid4()), 'event_type': 'recommendation_impression',
                    'paper_id': paper_id, 'source': 'recommendation',
                    'request_id': first['request_id'], 'rank': rank,
                }]}))

    async def _collect_events(self, paper_id=None):
        async with session_scope() as session:
            return list(await session.scalars(select(BehaviorEventRow.event_type).where(
                BehaviorEventRow.user_id == self.user_id,
                BehaviorEventRow.entity_id == (paper_id or self.paper_id),
                BehaviorEventRow.event_type.in_(['paper_collect', 'paper_uncollect']),
            ).order_by(BehaviorEventRow.received_at)))

    async def test_multi_folder_moves_and_folder_deletion_emit_only_real_transitions(self):
        collections = CollectionService()
        a, b, c = (await collections.folders(self.user_id)).folders[:3]
        await collections.update_paper_folders(self.user_id, self.paper_id, [a.id, b.id])
        await collections.move_paper(self.user_id, a.id, self.paper_id, c.id)
        await collections.move_paper(self.user_id, c.id, self.paper_id, b.id)
        await collections.update_paper_folders(self.user_id, self.paper_id, [c.id])
        self.assertEqual(await self._collect_events(), ['paper_collect'])
        extra = await collections.create_folder(self.user_id, 'extra')
        await collections.update_paper_folders(self.user_id, self.paper_id, [c.id, extra.id])
        await collections.delete_folder(self.user_id, extra.id)
        self.assertEqual(await self._collect_events(), ['paper_collect'])
        await collections.delete_folder(self.user_id, c.id)
        self.assertEqual(await self._collect_events(), ['paper_collect', 'paper_uncollect'])

    async def test_concurrent_collects_into_different_folders_record_one_interest(self):
        collections = CollectionService()
        folders = (await collections.folders(self.user_id)).folders
        await asyncio.gather(*(
            collections.update_paper_folders(self.user_id, self.paper_id, [folder.id]) for folder in folders
        ))
        self.assertEqual(await self._collect_events(), ['paper_collect'])
        self.assertEqual(len(await collections.paper_folders(self.user_id, self.paper_id)), 1)

    async def test_capacity_rejection_rolls_back_the_collect_event(self):
        collections = CollectionService()
        folder = (await collections.folders(self.user_id)).folders[0]
        async with session_scope() as session:
            from app.models.collections import CollectionItemRow
            for index in range(100):
                session.add(CollectionItemRow(folder_id=folder.id, paper_id=f'filler:{index}'))
        with self.assertRaises(BusinessError):
            await collections.update_paper_folders(self.user_id, self.paper_id, [folder.id])
        self.assertEqual(await self._collect_events(), [])

    async def test_account_deletion_removes_events_profile_and_snapshots(self):
        await PaperLikeService().like(self.user_id, self.paper_id)
        await UserProfileService(features=SimpleNamespace(get_many=AsyncMock(return_value={}))).rebuild(self.user_id)
        await self._service_with(self._candidates(2)).page(self.user_id, limit=1)
        await PaperLikeService().like(self.other_id, self.paper_id)
        await AccountDeletionService().delete_all_for_user(self.user_id)
        async with session_scope() as session:
            for model in (BehaviorEventRow, UserInterestProfileRow, RecommendationSnapshotRow):
                self.assertEqual(await session.scalar(select(func.count()).select_from(model).where(
                    model.user_id == self.user_id,
                )), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(BehaviorEventRow).where(
                BehaviorEventRow.user_id == self.other_id,
            )), 1)

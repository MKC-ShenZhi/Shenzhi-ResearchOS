"""Bounded multi-source paper recall and explainable content ranking."""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.core.time import utc_now
from app.models.collections import CollectionFolderRow, CollectionItemRow
from app.models.interactions import PaperLikeRow
from app.models.recommendation import RecommendationSnapshotRow
from app.models.stats import PaperStatDailyRow, StatsSnapshotRunRow
from app.schemas.knowledge import KnowledgeSearchRequest, PaperSearchResult
from app.services.discovery import HomeDiscoveryService
from app.services.knowledge.service import KnowledgeService, KnowledgeServiceError
from app.services.recommendation import config
from app.services.recommendation.config import (
    ALGORITHM_VERSION,
    MAX_RECALL_QUERIES,
    RANK_WEIGHTS,
    RECALL_PER_SOURCE,
)
from app.services.recommendation.profile import UserProfileService, _token

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    paper: dict
    subjects: list[str]
    keywords: list[str]
    sources: set[str]
    keyword_recall_match: float = 0.0


def _affinity(features: list[str], interests: dict[str, float]) -> float | None:
    if not features or not interests:
        return None
    return max((interests.get(_token(feature), 0.0) for feature in features), default=0.0)


def _rank(candidate: Candidate, profile: dict, popularity: float | None, year: int) -> tuple[float, str]:
    topics = {
        key: 0.6 * profile['long_topics'].get(key, 0) + 0.4 * profile['short_topics'].get(key, 0)
        for key in profile['long_topics'].keys() | profile['short_topics'].keys()
    }
    keywords = {
        key: 0.6 * profile['long_keywords'].get(key, 0) + 0.4 * profile['short_keywords'].get(key, 0)
        for key in profile['long_keywords'].keys() | profile['short_keywords'].keys()
    }
    follows = {_token(value) for value in profile['explicit_subjects']}
    direct_keyword_match = _affinity(candidate.keywords, keywords)
    features = {
        'topic_affinity': _affinity(candidate.subjects, topics),
        'keyword_match': max(direct_keyword_match or 0.0, candidate.keyword_recall_match)
            if keywords else None,
        'explicit_follow_match': (
            float(any(_token(value) in follows for value in candidate.subjects))
            if candidate.subjects and follows else None
        ),
        'popularity_score': popularity,
        'freshness_score': max(0.0, 1.0 - max(0, year - candidate.paper['year']) / 10)
            if candidate.paper.get('year') else None,
    }
    available = {key: value for key, value in features.items() if value is not None}
    denominator = sum(RANK_WEIGHTS[key] for key in available)
    score = sum(RANK_WEIGHTS[key] * value for key, value in available.items()) / denominator if denominator else 0.0
    has_personal_match = any((features[key] or 0) > 0 for key in (
        'topic_affinity', 'keyword_match', 'explicit_follow_match',
    ))
    if profile['has_history'] and not has_personal_match:
        score = min(score, 0.15)
    if features['explicit_follow_match']:
        reason = '与你关注的主题相匹配'
    elif features['topic_affinity'] and features['topic_affinity'] > 0:
        reason = '与你的研究主题相关'
    elif candidate.keyword_recall_match > (direct_keyword_match or 0):
        reason = '与你近期搜索的方向相关'
    elif features['keyword_match'] and features['keyword_match'] > 0:
        reason = '与你关注的论文关键词相关'
    elif popularity is not None and popularity > 0:
        reason = '近期受到平台用户关注'
    elif 'global_discovery' in candidate.sources:
        reason = '来自论文发现'
    else:
        reason = '来自相关论文检索'
    return round(score, 6), reason


class CandidateRecallService:
    def __init__(self, knowledge: KnowledgeService | None = None, discovery: HomeDiscoveryService | None = None):
        self.knowledge = knowledge or KnowledgeService()
        self.discovery = discovery or HomeDiscoveryService()

    async def recall(self, profile: dict) -> list[Candidate]:
        candidates: dict[str, Candidate] = {}
        followed = [('followed_topic', subject) for subject in profile['explicit_subjects']]
        combined = {
            key: 0.6 * profile['long_topics'].get(key, 0) + 0.4 * profile['short_topics'].get(key, 0)
            for key in profile['long_topics'].keys() | profile['short_topics'].keys()
        }
        inferred = [('inferred_topic', topic) for topic, score in sorted(
            combined.items(), key=lambda item: (-item[1], item[0]),
        ) if score > 0]
        combined_keywords = {
            key: 0.6 * profile['long_keywords'].get(key, 0) + 0.4 * profile['short_keywords'].get(key, 0)
            for key in profile['long_keywords'].keys() | profile['short_keywords'].keys()
        }
        keywords = [('keyword', keyword) for keyword, score in sorted(
            combined_keywords.items(), key=lambda item: (-item[1], item[0]),
        ) if score > 0]
        selected: list[tuple[str, str]] = []
        seen_queries: set[tuple[str, str]] = set()
        prioritized = followed[:2] + inferred[:1] + keywords[:1] + followed[2:] + inferred[1:] + keywords[1:]
        for kind, value in prioritized:
            marker = ('subject' if kind != 'keyword' else 'keyword', _token(value))
            if marker not in seen_queries:
                selected.append((kind, value))
                seen_queries.add(marker)
            if len(selected) == MAX_RECALL_QUERIES:
                break

        async def fetch(kind: str, value: str) -> tuple[str, str, list[PaperSearchResult]]:
            try:
                if kind == 'keyword':
                    result = await asyncio.wait_for(self.knowledge.search(
                        KnowledgeSearchRequest(query=value, topK=RECALL_PER_SOURCE),
                    ), timeout=config.RECALL_TIMEOUT_SECONDS)
                else:
                    result = await asyncio.wait_for(self.knowledge.search_by_subject(
                        value, limit=RECALL_PER_SOURCE,
                    ), timeout=config.RECALL_TIMEOUT_SECONDS)
                return kind, value, result.results
            except (KnowledgeServiceError, TimeoutError):
                return kind, value, []
            except Exception as error:  # noqa: BLE001 - one source must not sink the others
                # Unexpected adapter/contract failures are isolated per source.
                # Log only the type: the recall value can be a private search query.
                logger.warning('Recommendation recall source failed (%s, %s)', kind, type(error).__name__)
                return kind, value, []

        for kind, value, papers in await asyncio.gather(*(fetch(kind, value) for kind, value in selected)):
            for position, paper in enumerate(papers):
                entry = candidates.get(paper.id)
                if entry is None:
                    entry = Candidate(paper={
                        'id': paper.id, 'title': paper.title, 'abstract': paper.abstract or '',
                        'authors': paper.authors, 'year': paper.year,
                        'venue': paper.venue, 'pdf_url': None, 'thumbnail_url': None,
                    }, subjects=paper.subjects, keywords=paper.keywords, sources=set())
                    candidates[paper.id] = entry
                entry.sources.add(kind)
                if kind == 'keyword':
                    # Retrieval for an interest query is evidence even when
                    # upstream metadata omits the exact keyword phrase.
                    interest = combined_keywords.get(_token(value), 0.0)
                    entry.keyword_recall_match = max(
                        entry.keyword_recall_match, interest / (1 + position * 0.1),
                    )

        try:
            global_page = self.discovery.page(limit=config.GLOBAL_DISCOVERY_RECALL_LIMIT)
            for paper in global_page.items:
                entry = candidates.get(paper.id)
                if entry is None:
                    entry = Candidate(paper=paper.model_dump(mode='json'), subjects=[], keywords=[], sources=set())
                    candidates[paper.id] = entry
                entry.sources.add('global_discovery')
        except Exception as error:  # noqa: BLE001 - personal recall stays usable
            logger.warning(
                'Global discovery snapshot unavailable during recommendation recall (%s)',
                type(error).__name__,
            )
        return list(candidates.values())


class RecommendationService:
    def __init__(
        self, profiles: UserProfileService | None = None,
        recall: CandidateRecallService | None = None,
    ):
        self.profiles = profiles or UserProfileService()
        self.recall = recall or CandidateRecallService()

    async def page(self, user_id: str, *, limit: int, cursor: str | None = None) -> dict:
        if cursor:
            try:
                raw_id, raw_offset = cursor.split(':', 1)
                request_id, offset = UUID(raw_id), int(raw_offset)
            except (ValueError, TypeError) as error:
                raise BusinessError(20001, '推荐分页游标无效', 400) from error
            async with session_scope() as session:
                snapshot = await session.get(RecommendationSnapshotRow, request_id)
                # Purged, expired and other accounts' snapshots look identical.
                # Same stale-cursor contract as platform stats: 409 means this
                # cursor cannot be retried and the client restarts at page one.
                if snapshot is None or snapshot.user_id != user_id or snapshot.expires_at <= utc_now():
                    raise BusinessError(20001, '推荐列表已过期，请刷新后重新浏览', 409)
                items = snapshot.items
                version = snapshot.algorithm_version
        else:
            offset = 0
            profile = await self.profiles.get(user_id)
            candidates = await self.recall.recall(profile)
            excluded, popularity = await self._account_and_popularity(user_id, [item.paper['id'] for item in candidates])
            current_year = utc_now().year
            scored = []
            for candidate in candidates:
                if candidate.paper['id'] in excluded:
                    continue
                score, reason = _rank(candidate, profile, popularity.get(candidate.paper['id']), current_year)
                scored.append((score, candidate, reason))
            if profile['has_history']:
                scored.sort(key=lambda item: (-item[0], item[1].paper['id']))
                ordered = self._diversify(scored)
            else:
                # Preserve the established daily discovery order for cold start.
                ordered = scored
            request_id = uuid4()
            items = [{
                **candidate.paper, 'reason': reason,
                'sources': sorted(candidate.sources), 'request_id': str(request_id),
                'rank': rank,
            } for rank, (_score, candidate, reason) in enumerate(ordered, 1)]
            version = ALGORITHM_VERSION
            now = utc_now()
            async with session_scope() as session:
                session.add(RecommendationSnapshotRow(
                    request_id=request_id, user_id=user_id,
                    algorithm_version=version, created_at=now,
                    expires_at=now + timedelta(hours=1), items=items,
                ))
                await session.execute(delete(RecommendationSnapshotRow).where(
                    RecommendationSnapshotRow.user_id == user_id,
                    RecommendationSnapshotRow.expires_at < now,
                ))
        if offset < 0 or offset > len(items):
            raise BusinessError(20001, '推荐分页游标无效', 400)
        end = min(offset + limit, len(items))
        return {
            'items': items[offset:end],
            'next_cursor': f'{request_id}:{end}' if end < len(items) else None,
            'has_more': end < len(items), 'request_id': str(request_id),
            'total': len(items), 'algorithm_version': version,
        }

    @staticmethod
    def _diversify(scored: list[tuple[float, Candidate, str]]) -> list[tuple[float, Candidate, str]]:
        counts: dict[str, int] = defaultdict(int)
        remaining = list(scored)
        selected: list[tuple[float, Candidate, str]] = []
        while remaining:
            best_score, best_candidate, _ = remaining[0]
            best_topic = _token(best_candidate.subjects[0]) if best_candidate.subjects else ''
            choice = 0
            if best_topic and counts[best_topic] >= 4:
                for index, (score, candidate, _) in enumerate(remaining[1:], 1):
                    primary = _token(candidate.subjects[0]) if candidate.subjects else ''
                    if score < best_score * 0.8:
                        break
                    if primary and primary != best_topic and counts[primary] < 4:
                        choice = index
                        break
            item = remaining.pop(choice)
            primary = _token(item[1].subjects[0]) if item[1].subjects else ''
            if primary:
                counts[primary] += 1
            selected.append(item)
        return selected

    @staticmethod
    async def _account_and_popularity(user_id: str, paper_ids: list[str]) -> tuple[set[str], dict[str, float]]:
        if not paper_ids:
            return set(), {}
        async with session_scope() as session:
            liked = set(await session.scalars(select(PaperLikeRow.paper_id).where(
                PaperLikeRow.user_id == user_id, PaperLikeRow.paper_id.in_(paper_ids),
            )))
            collected = set(await session.scalars(select(CollectionItemRow.paper_id).join(
                CollectionFolderRow, CollectionFolderRow.id == CollectionItemRow.folder_id,
            ).where(CollectionFolderRow.user_id == user_id, CollectionItemRow.paper_id.in_(paper_ids))))
            latest = await session.scalar(select(func.max(StatsSnapshotRunRow.snapshot_date)).where(
                StatsSnapshotRunRow.status == 'completed',
            ))
            rows = [] if latest is None else list(await session.execute(select(
                PaperStatDailyRow.paper_id,
                PaperStatDailyRow.collector_count,
                PaperStatDailyRow.like_count,
            ).where(PaperStatDailyRow.snapshot_date == latest, PaperStatDailyRow.paper_id.in_(paper_ids))))
        counts = {paper_id: collectors + likes for paper_id, collectors, likes in rows}
        peak = max(counts.values(), default=0)
        popularity = {paper_id: count / peak for paper_id, count in counts.items()} if peak else {}
        return liked | collected, popularity

"""Bounded multi-source paper recall and explainable content ranking."""

import asyncio
import logging
from collections import Counter, defaultdict
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
from app.services.discovery_pool.sync import displayable_image_id
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


def _popularity_reason(popularity: float | None) -> str | None:
    return '近期受到平台用户关注' if popularity is not None and popularity > 0 else None


def _rank(
    candidate: Candidate, profile: dict, popularity: float | None, year: int,
) -> tuple[float, str | None]:
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
    else:
        # Without a real signal the card shows no reason instead of a generic label.
        reason = _popularity_reason(popularity)
    return round(score, 6), reason


def _blend(personal: list[dict], shared: list[dict]) -> list[dict]:
    """Interleave personal picks with the shared daily list, never repeating a paper."""
    blended: list[dict] = []
    seen: set[str] = set()
    personal_items, shared_items = iter(personal), iter(shared)

    def take(items, count: int) -> int:
        taken = 0
        while taken < count:
            item = next(items, None)
            if item is None:
                break
            if item['id'] not in seen:
                seen.add(item['id'])
                blended.append(item)
                taken += 1
        return taken

    while take(personal_items, config.PERSONAL_PER_SHARED) + take(shared_items, 1):
        pass
    return blended


class CandidateRecallService:
    """Personal candidates only; the shared daily list is blended in by RecommendationService."""

    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def recall(self, profile: dict, *, year: int | None = None) -> list[Candidate]:
        """Personal candidates; with `year`, only papers from the year the home feed shows.

        Knowledge images exist almost only for the home year, so unbounded
        retrieval would mostly return papers the image-only home feed drops.
        """
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
                    result = await asyncio.wait_for(self.knowledge.search(KnowledgeSearchRequest(
                        query=value, topK=RECALL_PER_SOURCE, yearFrom=year, yearTo=year,
                    )), timeout=config.RECALL_TIMEOUT_SECONDS)
                    return kind, value, result.results
                # Subject search has no year filter: over-fetch, then keep the home year.
                result = await asyncio.wait_for(self.knowledge.search_by_subject(
                    value, limit=RECALL_PER_SOURCE * (config.SUBJECT_YEAR_OVERFETCH if year else 1),
                ), timeout=config.RECALL_TIMEOUT_SECONDS)
                papers = [paper for paper in result.results if year is None or paper.year == year]
                return kind, value, papers[:RECALL_PER_SOURCE]
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
                        # Knowledge image id; the web layer resolves it to the image proxy.
                        'image_id': paper.image_id,
                        'keywords': paper.keywords, 'subjects': paper.subjects,
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
        return list(candidates.values())


class RecommendationService:
    def __init__(
        self, profiles: UserProfileService | None = None,
        recall: CandidateRecallService | None = None,
        discovery: HomeDiscoveryService | None = None,
    ):
        self.profiles = profiles or UserProfileService()
        self.recall = recall or CandidateRecallService()
        self.discovery = discovery or HomeDiscoveryService()

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
            shared = await self._shared_papers()
            years = Counter(paper['year'] for paper in shared if paper.get('year'))
            candidates = await self.recall.recall(profile, year=years.most_common(1)[0][0] if years else None)
            excluded, popularity = await self._account_and_popularity(
                user_id, [item.paper['id'] for item in candidates] + [paper['id'] for paper in shared],
            )
            static_thumbnails = {paper['id']: paper['thumbnail_url'] for paper in shared if paper.get('thumbnail_url')}
            current_year = utc_now().year
            scored = []
            for candidate in candidates:
                paper_id = candidate.paper['id']
                if paper_id in excluded:
                    continue
                # A curated paper recalled by search keeps its static thumbnail.
                candidate.paper['thumbnail_url'] = candidate.paper.get('thumbnail_url') or static_thumbnails.get(paper_id)
                if not (candidate.paper['thumbnail_url'] or displayable_image_id(candidate.paper.get('image_id'))):
                    continue  # The home feed only shows papers with an image the web proxy serves.
                score, reason = _rank(candidate, profile, popularity.get(paper_id), current_year)
                scored.append((score, candidate, reason))
            scored.sort(key=lambda item: (-item[0], item[1].paper['id']))
            personal = [{
                **candidate.paper, 'reason': reason, 'sources': sorted(candidate.sources),
            } for _score, candidate, reason in self._diversify(scored)[:config.PERSONAL_RECOMMENDATION_LIMIT]]
            shared_items = [{
                **paper, 'reason': _popularity_reason(popularity.get(paper['id'])),
                'sources': ['global_discovery'],
            } for paper in shared if paper['id'] not in excluded]
            request_id = uuid4()
            items = [{
                **item, 'request_id': str(request_id), 'rank': rank,
            } for rank, item in enumerate(_blend(personal, shared_items), 1)]
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

    async def _shared_papers(self) -> list[dict]:
        try:
            return [paper.model_dump(mode='json') for paper in await self.discovery.daily_papers()]
        except Exception as error:  # noqa: BLE001 - personal picks stay usable
            logger.warning('Shared daily papers unavailable for recommendations (%s)', type(error).__name__)
            return []

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

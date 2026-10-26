"""Rebuild current long and short research interests from account-owned facts."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import isfinite

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.collections import CollectionFolderRow, CollectionItemRow
from app.models.interactions import PaperLikeRow, TopicFollowRow
from app.models.reading_history import ReadingHistoryRow
from app.models.recommendation import BehaviorEventRow, UserInterestProfileRow
from app.services.recommendation.config import (
    ALGORITHM_VERSION,
    EVENT_WEIGHTS,
    HALF_LIFE_DAYS,
    MAX_PROFILE_PAPERS,
)
from app.services.recommendation.features import PaperFeatureService
from app.services.topics.registry import TopicRegistry, TopicRegistryError


def _token(value: str) -> str:
    return ' '.join(value.casefold().split())


def _normalized(values: dict[str, float]) -> dict[str, float]:
    peak = max(values.values(), default=0)
    return {key: round(score / peak, 5) for key, score in values.items() if score > 0} if peak > 0 else {}


def _decay(event_type: str, occurred_at: datetime, now: datetime) -> float:
    half_life = HALF_LIFE_DAYS.get(event_type)
    if half_life is None:
        return 1.0
    age_days = max(0.0, (now - occurred_at).total_seconds() / 86400)
    return 2 ** (-age_days / half_life)


def _accumulate(
    features: list[str], weight: float, occurred_at: datetime, event_type: str,
    now: datetime, long_scores: dict[str, float], short_scores: dict[str, float],
) -> None:
    if not features or not isfinite(weight) or weight <= 0:
        return
    distinct = {_token(value) for value in features if value.strip()}
    value = weight * _decay(event_type, occurred_at, now) / len(distinct) if distinct else 0
    for feature in distinct:
        long_scores[feature] += value
        # Short interests prioritize the last two weeks without erasing stable
        # likes, collections and follows from the long profile.
        if now - occurred_at <= timedelta(days=14):
            short_scores[feature] += value


class UserProfileService:
    def __init__(
        self, features: PaperFeatureService | None = None,
        topics: TopicRegistry | None = None,
    ):
        self.features = features or PaperFeatureService()
        self.topics = topics or TopicRegistry()

    async def get(self, user_id: str) -> dict:
        async with session_scope() as session:
            row = await session.get(UserInterestProfileRow, user_id)
            latest = await session.scalar(select(func.max(BehaviorEventRow.received_at)).where(
                BehaviorEventRow.user_id == user_id,
            ))
            if (row is not None and row.algorithm_version == ALGORITHM_VERSION
                and row.computed_at >= utc_now() - timedelta(minutes=10)
                and (latest is None or row.last_event_at == latest)):
                return row.profile_data
        return await self.rebuild(user_id)

    async def rebuild(self, user_id: str) -> dict:
        now = utc_now()
        async with session_scope() as session:
            likes = list((await session.execute(select(PaperLikeRow.paper_id, PaperLikeRow.created_at).where(
                PaperLikeRow.user_id == user_id,
            ).order_by(PaperLikeRow.created_at.desc()).limit(MAX_PROFILE_PAPERS))).all())
            collections = list((await session.execute(select(
                CollectionItemRow.paper_id, func.max(CollectionItemRow.created_at),
            ).join(CollectionFolderRow, CollectionFolderRow.id == CollectionItemRow.folder_id).where(
                CollectionFolderRow.user_id == user_id,
            ).group_by(CollectionItemRow.paper_id).order_by(func.max(CollectionItemRow.created_at).desc())
              .limit(MAX_PROFILE_PAPERS))).all())
            follows = list((await session.execute(select(TopicFollowRow.topic_id).where(
                TopicFollowRow.user_id == user_id,
            ))).scalars())
            reads = list((await session.execute(select(
                ReadingHistoryRow.paper_id, ReadingHistoryRow.read_at,
            ).where(
                ReadingHistoryRow.user_id == user_id,
                ReadingHistoryRow.read_at.is_not(None),
            ).order_by(ReadingHistoryRow.read_at.desc()).limit(MAX_PROFILE_PAPERS))).all())
            events = list((await session.execute(select(BehaviorEventRow).where(
                BehaviorEventRow.user_id == user_id,
                BehaviorEventRow.received_at >= now - timedelta(days=90),
                BehaviorEventRow.event_type.in_(EVENT_WEIGHTS.keys()),
                BehaviorEventRow.source != 'explicit',
            ).order_by(BehaviorEventRow.received_at.desc()).limit(500))).scalars())
            latest = await session.scalar(select(func.max(BehaviorEventRow.received_at)).where(
                BehaviorEventRow.user_id == user_id,
            ))

        paper_ids = list(dict.fromkeys(
            [paper_id for paper_id, _ in collections + likes + reads]
            + [event.entity_id for event in events if event.entity_type == 'paper']
        ))[:MAX_PROFILE_PAPERS]
        papers = await self.features.get_many(paper_ids)
        long_topics: dict[str, float] = defaultdict(float)
        short_topics: dict[str, float] = defaultdict(float)
        long_keywords: dict[str, float] = defaultdict(float)
        short_keywords: dict[str, float] = defaultdict(float)
        explicit_subjects: list[str] = []
        for topic_id in follows:
            try:
                subject = self.topics.get_topic(topic_id).subject_query
            except TopicRegistryError:
                continue
            explicit_subjects.append(subject)
            long_topics[_token(subject)] += EVENT_WEIGHTS['topic_follow']
            short_topics[_token(subject)] += EVENT_WEIGHTS['topic_follow']

        search_queries: dict[str, datetime] = {}
        for event in events:
            if event.event_type == 'search_submit' and event.entity_type == 'query':
                search_queries.setdefault(_token(event.entity_id), event.received_at)
            if len(search_queries) >= 10:
                break
        for query, occurred_at in search_queries.items():
            short_keywords[query] += EVENT_WEIGHTS['search_submit'] * _decay('search_submit', occurred_at, now)

        signals = [(paper_id, created, 'paper_collect') for paper_id, created in collections]
        signals.extend((paper_id, created, 'paper_like') for paper_id, created in likes)
        signals.extend((paper_id, created, 'paper_read') for paper_id, created in reads)
        # The same navigation can emit click and detail events. Keep only the
        # stronger one per paper and day, and cap repeated weak actions.
        weak: dict[tuple[str, str], BehaviorEventRow] = {}
        for event in events:
            day = event.received_at.date().isoformat()
            key = (event.entity_id, day)
            previous = weak.get(key)
            if previous is None or EVENT_WEIGHTS[event.event_type] > EVENT_WEIGHTS[previous.event_type]:
                weak[key] = event
        signals.extend((event.entity_id, event.received_at, event.event_type)
                       for event in weak.values() if event.entity_type == 'paper')
        for paper_id, created, event_type in signals:
            paper = papers.get(paper_id)
            if paper is None:
                continue
            timestamp = created.replace(tzinfo=UTC) if created.tzinfo is None else created
            weight = EVENT_WEIGHTS[event_type]
            _accumulate(paper.subjects, weight, timestamp, event_type, now, long_topics, short_topics)
            _accumulate(paper.keywords, weight, timestamp, event_type, now, long_keywords, short_keywords)

        profile = {
            'algorithm_version': ALGORITHM_VERSION,
            'computed_at': now.isoformat(),
            'long_topics': _normalized(long_topics),
            'short_topics': _normalized(short_topics),
            'long_keywords': _normalized(long_keywords),
            'short_keywords': _normalized(short_keywords),
            'explicit_subjects': sorted(set(explicit_subjects)),
            'has_history': bool(likes or collections or follows or reads or weak or search_queries),
        }
        async with session_scope() as session:
            statement = insert(UserInterestProfileRow).values(
                user_id=user_id, algorithm_version=ALGORITHM_VERSION,
                computed_at=now, last_event_at=latest, profile_data=profile,
            )
            await session.execute(statement.on_conflict_do_update(
                index_elements=['user_id'],
                set_={
                    'algorithm_version': ALGORITHM_VERSION,
                    'computed_at': now,
                    'last_event_at': latest,
                    'profile_data': profile,
                    'profile_version': UserInterestProfileRow.profile_version + 1,
                },
            ))
        return profile

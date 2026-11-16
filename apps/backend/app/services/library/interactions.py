"""Batch composition of public counters and the current user's own state."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.library.collections import CollectionService
from app.services.library.paper_likes import PaperLikeService
from app.services.library.topic_follows import TopicFollowService


@dataclass(frozen=True)
class PaperInteraction:
    paper_id: str
    collector_count: int
    like_count: int
    folder_ids: list[int] | None = None
    liked: bool | None = None


@dataclass(frozen=True)
class TopicInteraction:
    topic_id: str
    follower_count: int
    is_following: bool | None = None


async def _no_folders() -> dict[str, list[int]]:
    return {}


async def _no_likes() -> set[str]:
    return set()


class InteractionService:
    """One call answers a whole visible list; personal fields need a user id.

    Anonymous callers only receive public counters. The user id must come from
    the trusted BFF identity, never from the request body or query string.
    """

    def __init__(
        self,
        collections: CollectionService | None = None,
        likes: PaperLikeService | None = None,
        follows: TopicFollowService | None = None,
    ):
        self.collections = collections or CollectionService()
        self.likes = likes or PaperLikeService()
        self.follows = follows or TopicFollowService()

    async def paper_states(self, user_id: str | None, paper_ids: list[str]) -> list[PaperInteraction]:
        ids = list(dict.fromkeys(paper_ids))
        if not ids:
            return []
        collector_counts, like_counts, folder_map, liked_ids = await asyncio.gather(
            self.collections.collector_counts(ids),
            self.likes.like_counts(ids),
            self.collections.paper_folder_map(user_id, ids) if user_id else _no_folders(),
            self.likes.liked_paper_ids(user_id, ids) if user_id else _no_likes(),
        )
        return [
            PaperInteraction(
                paper_id=paper_id,
                collector_count=collector_counts.get(paper_id, 0),
                like_count=like_counts.get(paper_id, 0),
                folder_ids=folder_map.get(paper_id, []) if user_id else None,
                liked=(paper_id in liked_ids) if user_id else None,
            )
            for paper_id in ids
        ]

    async def topic_states(self, user_id: str | None, topic_ids: list[str]) -> list[TopicInteraction]:
        ids = list(dict.fromkeys(topic_ids))
        if not ids:
            return []
        follower_counts, following_ids = await asyncio.gather(
            self.follows.follower_counts(ids),
            self.follows.followed_topic_ids(user_id, ids) if user_id else _no_likes(),
        )
        return [
            TopicInteraction(
                topic_id=topic_id,
                follower_count=follower_counts.get(topic_id, 0),
                is_following=(topic_id in following_ids) if user_id else None,
            )
            for topic_id in ids
        ]

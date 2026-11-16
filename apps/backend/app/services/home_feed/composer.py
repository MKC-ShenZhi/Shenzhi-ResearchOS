"""Merge bounded home-feed sources into one ordered, de-duplicated list.

Each source hands over an already ordered list. Sources are interleaved by
their per-screen quota (smooth weighted round-robin), so an exhausted
source's slots are filled by the others in proportion. A paper offered by
several sources keeps its first placement. Finally no screen shows one venue
more than VENUE_PER_SCREEN times.

The result depends only on the inputs, so the same day's anonymous list is
identical on every server instance without being stored.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from app.schemas.discovery import DiscoveryPaper
from app.services.home_feed import config


def spread_venues(papers: list[DiscoveryPaper]) -> list[DiscoveryPaper]:
    """Reorder so no screen of SCREEN_SIZE cards shows one venue more than VENUE_PER_SCREEN times.

    Swaps forward first; papers left over at the end of the list are swapped
    with an earlier screen that can take them without breaking its own limit.
    """
    papers = list(papers)
    size, cap = config.SCREEN_SIZE, config.VENUE_PER_SCREEN

    def screen_counts(index: int) -> Counter:
        start = index - index % size
        return Counter(paper.venue for paper in papers[start:start + size])

    for index in range(len(papers)):
        screen_start = index - index % size
        counts = Counter(paper.venue for paper in papers[screen_start:index])
        if counts[papers[index].venue] < cap:
            continue
        for later in range(index + 1, len(papers)):
            if counts[papers[later].venue] < cap:
                papers[index], papers[later] = papers[later], papers[index]
                break
    for index in range(len(papers)):
        venue = papers[index].venue
        if screen_counts(index)[venue] <= cap:
            continue
        for earlier in range(index - index % size - 1, -1, -1):
            other = papers[earlier].venue
            if other != venue and screen_counts(earlier)[venue] < cap and screen_counts(index)[other] < cap:
                papers[index], papers[earlier] = papers[earlier], papers[index]
                break
    return papers


def compose(
    sources: Mapping[str, Sequence[DiscoveryPaper]],
    quotas: Mapping[str, int],
    *,
    limit: int = config.FEED_LIMIT,
) -> list[DiscoveryPaper]:
    """Interleave `sources` by `quotas`; each returned paper carries its `source`."""
    weights = {name: quota for name, quota in quotas.items() if quota > 0 and sources.get(name)}
    queues = {name: list(sources[name]) for name in weights}
    # Smooth weighted round-robin over the sources that still have papers: a
    # screen of sum(quotas) slots gets exactly each quota, and an exhausted
    # source's share is spread over the rest at once, without catch-up bursts.
    credit: Counter = Counter()
    seen: set[str] = set()
    ordered: list[DiscoveryPaper] = []
    while len(ordered) < limit:
        active = [name for name, queue in queues.items() if queue]
        if not active:
            break
        for name in active:
            credit[name] += weights[name]
        name = max(active, key=lambda name: credit[name])  # ties go to the first listed
        credit[name] -= sum(weights[active_name] for active_name in active)
        paper = queues[name].pop(0)
        if paper.id in seen:
            continue
        seen.add(paper.id)
        ordered.append(paper.model_copy(update={'source': name}))
    return spread_venues(ordered)

"""Small-sample recommendation diagnostics without exposing user histories."""

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.database import dispose_engine, session_scope
from app.core.time import utc_now
from app.models.recommendation import BehaviorEventRow

MAX_EVENTS = 100_000


def engagement_summary(events: Iterable[BehaviorEventRow]) -> dict:
    """Count distinct recommendation exposures and clicks by snapshot position."""
    events = list(events)
    impressions: set[tuple[str, str | None, str, int | None]] = set()
    clicks: set[tuple[str, str | None, str, int | None]] = set()
    impression_events = 0
    click_events = 0
    for event in events:
        key = (event.user_id, event.request_id, event.entity_id, event.rank)
        if event.event_type == 'recommendation_impression':
            impression_events += 1
            impressions.add(key)
        elif event.event_type == 'recommendation_click':
            click_events += 1
            clicks.add(key)
    matched = len(clicks & impressions)
    return {
        'unique_impressions': len(impressions),
        'unique_clicks': len(clicks),
        'clicks_with_impression': matched,
        'clicks_without_impression': len(clicks) - matched,
        'repeated_impression_events': impression_events - len(impressions),
        'repeated_click_events': click_events - len(clicks),
        'click_through_rate': round(matched / len(impressions), 6) if impressions else None,
        'search_linkage': search_linkage_summary(events),
    }


def search_linkage_summary(events: Iterable[BehaviorEventRow]) -> dict:
    """Report search click attribution counts without returning query/user data."""
    materialized = list(events)
    submissions = {
        (event.user_id, getattr(event, 'query_id', None))
        for event in materialized
        if event.event_type == 'search_submit' and getattr(event, 'query_id', None) is not None
    }
    clicks = [event for event in materialized if event.event_type == 'search_result_click']
    with_query_id = [event for event in clicks if getattr(event, 'query_id', None) is not None]
    linked = sum(
        (event.user_id, event.query_id) in submissions
        for event in with_query_id
    )
    return {
        'search_result_clicks': len(clicks),
        'clicks_with_matching_search_submit': linked,
        'clicks_without_query_id': len(clicks) - len(with_query_id),
        'clicks_with_unmatched_query_id': len(with_query_id) - linked,
    }


def judged_quality(ranked_ids: list[str], relevant_ids: set[str], k: int) -> dict:
    """Evaluate one explicitly judged candidate set; never infer relevance from clicks."""
    if k < 1:
        raise ValueError('k must be positive')
    if not relevant_ids:
        return {'recall_at_k': None, 'ndcg_at_k': None}
    top = ranked_ids[:k]
    recall = len(set(top) & relevant_ids) / len(relevant_ids)
    dcg = sum(1 / math.log2(position + 2) for position, paper_id in enumerate(top)
              if paper_id in relevant_ids)
    ideal = sum(1 / math.log2(position + 2) for position in range(min(k, len(relevant_ids))))
    return {'recall_at_k': round(recall, 6), 'ndcg_at_k': round(dcg / ideal, 6)}


def compare_judged_baselines(dataset: dict, ks: list[int]) -> dict:
    """Compare precomputed rankings on identical, human-judged candidate sets.

    Input shape: {"cases": [{"relevant_ids": [...], "rankings": {name: [...]}}]}.
    Candidate IDs must be unique and identical across methods for each case.
    """
    if not ks or any(k < 1 for k in ks):
        raise ValueError('k values must be positive')
    cases = dataset.get('cases') if isinstance(dataset, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError('dataset must contain a non-empty cases list')

    totals: dict[str, dict[int, dict[str, float]]] = {}
    evaluated = 0
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise TypeError(f'case {index} must be an object')
        relevant = case.get('relevant_ids')
        rankings = case.get('rankings')
        if (not isinstance(relevant, list) or not relevant
            or any(not isinstance(paper_id, str) or not paper_id for paper_id in relevant)):
            raise ValueError(f'case {index} needs at least one judged relevant paper')
        if not isinstance(rankings, dict) or len(rankings) < 2:
            raise ValueError(f'case {index} needs rankings for at least two baselines')
        relevant_ids = set(relevant)
        candidate_sets: list[set[str]] = []
        for name, ranking in rankings.items():
            if (not isinstance(name, str) or not name or not isinstance(ranking, list) or not ranking
                or any(not isinstance(paper_id, str) or not paper_id for paper_id in ranking)):
                raise ValueError(f'case {index} has an invalid ranking')
            if len(set(ranking)) != len(ranking):
                raise ValueError(f'case {index} ranking {name!r} contains duplicate paper IDs')
            candidate_sets.append(set(ranking))
        if any(candidate_set != candidate_sets[0] for candidate_set in candidate_sets[1:]):
            raise ValueError(f'case {index} rankings must contain the same candidate set')
        if not relevant_ids.issubset(candidate_sets[0]):
            raise ValueError(f'case {index} relevance labels include papers outside the candidate set')

        evaluated += 1
        for name, ranking in rankings.items():
            method_totals = totals.setdefault(name, {k: {'recall': 0.0, 'ndcg': 0.0} for k in ks})
            for k in ks:
                metrics = judged_quality(ranking, relevant_ids, k)
                method_totals[k]['recall'] += metrics['recall_at_k'] or 0.0
                method_totals[k]['ndcg'] += metrics['ndcg_at_k'] or 0.0

    return {
        'evaluated_cases': evaluated,
        'candidate_set_policy': 'identical_per_case',
        'metrics': {
            name: {
                f'@{k}': {
                    'recall': round(values[k]['recall'] / evaluated, 6),
                    'ndcg': round(values[k]['ndcg'] / evaluated, 6),
                }
                for k in ks
            }
            for name, values in sorted(totals.items())
        },
    }


def compare_judgments_file(path: Path, ks: list[int]) -> dict:
    try:
        dataset = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f'cannot read judgment dataset: {error}') from error
    return compare_judged_baselines(dataset, ks)


async def recent_engagement(days: int = 7) -> dict:
    if not 1 <= days <= 90:
        raise ValueError('days must be between 1 and 90')
    async with session_scope() as session:
        events = list(await session.scalars(select(BehaviorEventRow).where(
            BehaviorEventRow.event_type.in_([
                'recommendation_impression', 'recommendation_click',
                'search_submit', 'search_result_click',
            ]),
            BehaviorEventRow.received_at >= utc_now() - timedelta(days=days),
        ).order_by(BehaviorEventRow.received_at.desc()).limit(MAX_EVENTS + 1)))
    complete = len(events) <= MAX_EVENTS
    result = engagement_summary(events[:MAX_EVENTS])
    return {'window_days': days, 'sample_complete': complete,
            'events_examined': min(len(events), MAX_EVENTS), **result}


async def main() -> int:
    try:
        print(json.dumps(await recent_engagement(), ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        await dispose_engine()


def cli() -> int:
    parser = argparse.ArgumentParser(description='Audit recommendation/search engagement or compare judged baselines.')
    parser.add_argument('--judgments', type=Path, help='JSON file with same-candidate-set rankings and human labels')
    parser.add_argument('--k', type=int, nargs='+', default=[5, 10], help='cutoffs for Recall@K and NDCG@K')
    args = parser.parse_args()
    if args.judgments:
        try:
            print(json.dumps(compare_judgments_file(args.judgments, args.k), ensure_ascii=False, sort_keys=True))
            return 0
        except ValueError as error:
            print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
            return 2
    return asyncio.run(main())


if __name__ == '__main__':
    sys.exit(cli())

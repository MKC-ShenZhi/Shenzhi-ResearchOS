"""Versioned, deliberately simple first-stage recommendation parameters."""

ALGORITHM_VERSION = 'content-v1'
EVENT_WEIGHTS = {
    'paper_collect': 4.0,
    'paper_like': 2.0,
    'topic_follow': 3.0,
    'active_read': 1.5,
    'paper_read': 1.0,
    'abstract_expand': 0.8,
    'paper_detail_view': 0.5,
    'paper_click': 0.3,
    'search_result_click': 0.5,
    'recommendation_click': 0.5,
    'search_submit': 0.2,
}
HALF_LIFE_DAYS = {
    'paper_collect': 90,
    'paper_like': 45,
    'active_read': 14,
    'paper_read': 14,
    'abstract_expand': 14,
    'paper_detail_view': 7,
    'paper_click': 7,
    'search_result_click': 7,
    'recommendation_click': 7,
    'search_submit': 3,
}
PROFILE_IMMEDIATE_EVENT_TYPES = frozenset({
    'paper_collect', 'paper_uncollect', 'paper_like', 'paper_unlike',
    'topic_follow', 'topic_unfollow', 'paper_read', 'active_read',
    'search_submit',
})
RANK_WEIGHTS = {
    'topic_affinity': 0.40,
    'keyword_match': 0.25,
    'explicit_follow_match': 0.20,
    'popularity_score': 0.10,
    'freshness_score': 0.05,
}
MAX_PROFILE_PAPERS = 40
MAX_RECALL_QUERIES = 4
RECALL_PER_SOURCE = 12
# Each recall query and each metadata lookup is bounded independently, so one
# slow upstream path degrades to fewer candidates instead of a failed page.
RECALL_TIMEOUT_SECONDS = 5.0
GLOBAL_DISCOVERY_RECALL_LIMIT = 48
METADATA_TIMEOUT_SECONDS = 4.0
METADATA_BATCH_TIMEOUT_SECONDS = 6.0
METADATA_CONCURRENCY = 4

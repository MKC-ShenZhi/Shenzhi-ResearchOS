# Search and recommendation judgments

## `robot-visuomotor-v0`

This is a small, provisional binary relevance case for the query **“Diffusion-based visuomotor imitation learning for robotic manipulation.”** It contains a 13-paper pooled candidate set: five current global-discovery items and the mock-catalog papers returned by the explicit-topic and content-v1 paths. Labels were assigned from titles and abstracts using the rule stored in the JSON; click and impression events were not used as relevance labels.

The current labels are a single-reviewer manual first pass authored by Codex. They are **not yet human-annotated ground truth** and require review by a robotics/recommendation domain reviewer before any product or model decision. The dataset records this status explicitly so the provisional metrics cannot be mistaken for a validated benchmark.

Ranking provenance:

- `global_discovery`: first five from `HomeDiscoveryService.page` in the current local snapshot; pooled candidates absent from that prefix follow in stable ID order.
- `explicit_topic`: `KnowledgeService.search_by_subject("Imitation Learning")` response order from a deterministic test-only local Knowledge API fixture; remaining pooled IDs follow in stable order.
- `content-v1`: first eight from `RecommendationService.page` for the synthetic isolated-test account after a Diffusion Policy search and foreground PDF read; remaining pooled IDs follow in stable order.

The explicit-topic and content-v1 captures came from the local deterministic fixture and mock paper corpus, not the production Knowledge Base. The ranking fixture was created only to make the current evaluator comparable on the same candidate set. One query and one reviewer do not support statistical generalization. Expand this set across multiple queries, topic categories, and independent reviewers; adjudicate disagreements before treating the metrics as a quality baseline.

## Reproduce metrics

From `apps/backend`, run:

```powershell
python -m app.services.recommendation.evaluation --judgments evaluation/recommendation-judgments/robot-visuomotor-v0.json --k 3 5 10
```

The command uses the checked-in candidate rankings and labels only; it does not connect to PostgreSQL. It validates that every method ranks the same unique candidate IDs and prints macro Recall@K and binary NDCG@K. The saved output is `robot-visuomotor-v0.metrics.json`.

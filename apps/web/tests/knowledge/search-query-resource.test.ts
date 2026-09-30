import assert from "node:assert/strict";
import test from "node:test";

import { QueryClient, QueryObserver } from "@tanstack/react-query";
import type {
  KnowledgeClient,
  KnowledgeSearchParams,
  KnowledgeSearchResponse,
} from "../../clients/knowledge/index.js";
import {
  cancelObsoleteKnowledgeSearches,
  KNOWLEDGE_SEARCH_CACHE_TTL_MS,
  knowledgeSearchCacheKey,
  knowledgeSearchQueryKey,
  knowledgeSearchQueryOptions,
  startKnowledgeSearch,
} from "../../features/knowledge/search/search-query-resource.js";

const BASE_PARAMS: KnowledgeSearchParams = {
  query: "graph neural network",
  topK: 20,
  offset: 0,
  yearFrom: 2020,
  yearTo: 2026,
  venue: ["NeurIPS", "ICLR"],
  author: ["Ada"],
  keyword: ["graph"],
  subject: ["machine learning"],
};

const EMPTY_RESPONSE: KnowledgeSearchResponse = { results: [], hasMore: false };

function clientWithSearch(
  search: (
    params: KnowledgeSearchParams,
    signal?: AbortSignal,
  ) => Promise<KnowledgeSearchResponse>,
): KnowledgeClient {
  return { search } as KnowledgeClient;
}

test("search cache key is stable for trimmed, duplicated and reordered array filters", () => {
  const reordered: KnowledgeSearchParams = {
    ...BASE_PARAMS,
    query: "  graph neural network  ",
    venue: [" ICLR ", "NeurIPS", "ICLR"],
    author: ["Ada", "Ada"],
  };

  assert.equal(knowledgeSearchCacheKey(BASE_PARAMS), knowledgeSearchCacheKey(reordered));
  assert.deepEqual(knowledgeSearchQueryKey(BASE_PARAMS), knowledgeSearchQueryKey(reordered));
  assert.notEqual(
    knowledgeSearchCacheKey(BASE_PARAMS),
    knowledgeSearchCacheKey({ ...BASE_PARAMS, yearFrom: 2021 }),
  );
});

test("fresh cache respects the two-minute TTL and stale cache refetches", async () => {
  const queryClient = new QueryClient();
  const key = knowledgeSearchQueryKey(BASE_PARAMS);
  let requests = 0;
  const client = clientWithSearch(async () => {
    requests += 1;
    return EMPTY_RESPONSE;
  });

  queryClient.setQueryData(key, EMPTY_RESPONSE, { updatedAt: Date.now() });
  await startKnowledgeSearch(queryClient, BASE_PARAMS, client);
  assert.equal(requests, 0);

  queryClient.setQueryData(key, EMPTY_RESPONSE, {
    updatedAt: Date.now() - KNOWLEDGE_SEARCH_CACHE_TTL_MS - 1,
  });
  await startKnowledgeSearch(queryClient, BASE_PARAMS, client);
  assert.equal(requests, 1);
  queryClient.clear();
});

test("same-key callers reuse one in-flight backend request", async () => {
  const queryClient = new QueryClient();
  let requests = 0;
  let resolveRequest!: (value: KnowledgeSearchResponse) => void;
  const client = clientWithSearch(() => {
    requests += 1;
    return new Promise((resolve) => {
      resolveRequest = resolve;
    });
  });

  const first = startKnowledgeSearch(queryClient, BASE_PARAMS, client);
  const second = startKnowledgeSearch(queryClient, {
    ...BASE_PARAMS,
    venue: [...BASE_PARAMS.venue].reverse(),
  }, client);

  assert.equal(requests, 1);
  resolveRequest(EMPTY_RESPONSE);
  assert.deepEqual(await first, EMPTY_RESPONSE);
  assert.deepEqual(await second, EMPTY_RESPONSE);
  queryClient.clear();
});

test("stale cache is visible while a background revalidation replaces it", async () => {
  const queryClient = new QueryClient();
  const stale: KnowledgeSearchResponse = {
    results: [{
      id: "paper:stale",
      title: "Cached paper",
      abstract: null,
      authors: [],
      year: null,
      venue: null,
      keywords: [],
      subjects: [],
      score: null,
      rank: null,
      provenance: null,
    }],
    hasMore: false,
  };
  let resolveRequest!: (value: KnowledgeSearchResponse) => void;
  const client = clientWithSearch(() => new Promise((resolve) => {
    resolveRequest = resolve;
  }));
  const key = knowledgeSearchQueryKey(BASE_PARAMS);
  queryClient.setQueryData(key, stale, {
    updatedAt: Date.now() - KNOWLEDGE_SEARCH_CACHE_TTL_MS - 1,
  });

  const observer = new QueryObserver(
    queryClient,
    knowledgeSearchQueryOptions(BASE_PARAMS, client),
  );
  const refreshed = new Promise<void>((resolve) => {
    const unsubscribe = observer.subscribe((result) => {
      if (!result.isFetching && result.data?.results.length === 0) {
        unsubscribe();
        resolve();
      }
    });
  });

  assert.equal(observer.getCurrentResult().data, stale);
  assert.equal(observer.getCurrentResult().isFetching, true);
  resolveRequest(EMPTY_RESPONSE);
  await refreshed;
  assert.deepEqual(observer.getCurrentResult().data, EMPTY_RESPONSE);
  queryClient.clear();
});

test("changing conditions aborts obsolete work but keeps the current key alive", async () => {
  const queryClient = new QueryClient();
  let aborted = false;
  const client = clientWithSearch((_params, signal) => new Promise((_resolve, reject) => {
    signal?.addEventListener("abort", () => {
      aborted = true;
      reject(signal.reason);
    }, { once: true });
  }));

  const pending = startKnowledgeSearch(queryClient, BASE_PARAMS, client);
  const cancelled = assert.rejects(pending);
  await cancelObsoleteKnowledgeSearches(queryClient, {
    ...BASE_PARAMS,
    query: "transformer",
  });

  assert.equal(aborted, true);
  await cancelled;
  queryClient.clear();
});

test("a cancelled stale response cannot populate or replace the latest query", async () => {
  const queryClient = new QueryClient();
  let resolveOld!: (value: KnowledgeSearchResponse) => void;
  const oldResponse: KnowledgeSearchResponse = { results: [], hasMore: true };
  const oldClient = clientWithSearch(() => new Promise((resolve) => {
    // Deliberately ignore AbortSignal to exercise the stale-response guard.
    resolveOld = resolve;
  }));
  const latestParams = { ...BASE_PARAMS, query: "transformer" };
  const oldPending = startKnowledgeSearch(queryClient, BASE_PARAMS, oldClient);
  const oldCancelled = assert.rejects(oldPending);

  await cancelObsoleteKnowledgeSearches(queryClient, latestParams);
  await startKnowledgeSearch(
    queryClient,
    latestParams,
    clientWithSearch(async () => EMPTY_RESPONSE),
  );
  resolveOld(oldResponse);
  await oldCancelled;
  await Promise.resolve();

  assert.equal(queryClient.getQueryData(knowledgeSearchQueryKey(BASE_PARAMS)), undefined);
  assert.equal(queryClient.getQueryData(knowledgeSearchQueryKey(latestParams)), EMPTY_RESPONSE);
  queryClient.clear();
});

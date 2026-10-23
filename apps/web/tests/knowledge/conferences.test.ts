import assert from "node:assert/strict";
import test from "node:test";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { BffKnowledgeClient, type KnowledgeClient, type KnowledgeConference, type KnowledgePaperBrowseResponse } from "../../clients/knowledge";
import { buildConferenceDirectoryUrl, buildPaperBrowseUrl, CONFERENCE_PAGE_SIZE, FEATURED_CONFERENCES, filterConferences, readConferenceDirectoryState, readPaperBrowseState, resolveConference, resolveConferenceYear } from "../../features/knowledge/search/conferences/conference-state";
import { conferenceQueryOptions, paperBrowseQueryOptions } from "../../features/knowledge/search/conferences/conference-queries";
import { createSearchRestoration } from "../../lib/navigation/search-restoration";
import { readSearchScroll, saveSearchScroll } from "../../features/knowledge/search/search-scroll-state";

const ITEMS: KnowledgeConference[] = [
  { name: "AAAI", paperCount: 31, yearCount: 2, years: [2026, 2022] },
  { name: "AAAI alias", paperCount: 3, yearCount: 1, years: [2021] },
  { name: "CVPR", paperCount: 50, yearCount: 2, years: [2025, 2023] },
];

test("default browse, legacy keyword URLs, and explicit modes remain isolated", () => {
  assert.equal(readPaperBrowseState(new URLSearchParams()).mode, "conference");
  assert.equal(readPaperBrowseState(new URLSearchParams("q=graph&venue=AAAI")).mode, "keyword");
  assert.equal(readPaperBrowseState(new URLSearchParams("mode=keyword")).mode, "keyword");
  assert.equal(readPaperBrowseState(new URLSearchParams("mode=conference&q=graph")).mode, "conference");
  const url = buildPaperBrowseUrl("A & B/会议", 2022, 3);
  const state = readPaperBrowseState(new URL(url, "https://local.test").searchParams);
  assert.deepEqual(state, { mode: "conference", conference: "A & B/会议", year: 2022, page: 3 });
  assert.doesNotMatch(url, /q=|venue=|yearFrom=/);
});

test("switching conferences selects the latest actual year and never fills gaps", () => {
  assert.deepEqual(FEATURED_CONFERENCES, ["AAAI", "CVPR", "ICML", "ACL", "NeurIPS", "ICLR"]);
  assert.equal(resolveConference(ITEMS, "")?.name, "AAAI");
  assert.equal(resolveConference(ITEMS, "AAAI alias")?.paperCount, 3);
  assert.equal(resolveConference(ITEMS, "UNKNOWN"), undefined);
  assert.equal(resolveConferenceYear(ITEMS[0], 2023), 2026);
  assert.equal(resolveConferenceYear(ITEMS[0], 2022), 2022);
  assert.equal(resolveConferenceYear(ITEMS[2], 2022), 2025);
});

test("directory searches names, filters actual years, sorts without mutating metadata", () => {
  const state = readConferenceDirectoryState(new URLSearchParams("q=aaai&year=2022&sort=name&page=2"));
  assert.deepEqual(filterConferences(ITEMS, state).map((item) => item.name), ["AAAI"]);
  assert.deepEqual(filterConferences(ITEMS, { ...state, year: 2024 }), []);
  assert.deepEqual(filterConferences(ITEMS, { ...state, query: "", year: 0, sort: "count" }).map((item) => item.name), ["CVPR", "AAAI", "AAAI alias"]);
  assert.deepEqual(filterConferences(ITEMS, { ...state, query: "", year: 0, sort: "name" }).map((item) => item.name), ["AAAI", "AAAI alias", "CVPR"]);
  assert.equal(ITEMS[0].name, "AAAI");
  assert.equal(CONFERENCE_PAGE_SIZE, 21);
  assert.deepEqual(readConferenceDirectoryState(new URL(buildConferenceDirectoryUrl(state), "https://local.test").searchParams), state);
});

test("BFF browse forwards exact conference, pagination, cancellation and no keyword", async () => {
  const original = globalThis.fetch;
  const requests: string[] = [];
  const controller = new AbortController();
  globalThis.fetch = async (input, init) => {
    requests.push(String(input));
    assert.equal(init?.signal, controller.signal);
    return new Response(JSON.stringify({ code: 0, data: requests.length === 1 ? { items: ITEMS } : { results: [], total: 0, limit: 20, offset: 20 } }));
  };
  try {
    const client = new BffKnowledgeClient();
    assert.equal((await client.conferences(controller.signal)).items.length, 3);
    await client.browsePapers({ conference: "A & B", year: 2022, limit: 20, offset: 20 }, controller.signal);
    assert.deepEqual(requests, ["/api/v1/knowledge/conferences", "/api/v1/knowledge/papers?conference=A+%26+B&year=2022&limit=20&offset=20"]);
  } finally { globalThis.fetch = original; }
});

test("directory and home share metadata cache for ten minutes", async () => {
  const cache = new QueryClient();
  let requests = 0;
  const client = { conferences: async () => { requests++; return { items: ITEMS }; } } as unknown as KnowledgeClient;
  await Promise.all([cache.fetchQuery(conferenceQueryOptions(client)), cache.fetchQuery(conferenceQueryOptions(client))]);
  await cache.fetchQuery(conferenceQueryOptions(client));
  assert.equal(requests, 1);
  assert.equal(conferenceQueryOptions(client).staleTime, 600_000);
  cache.clear();
});

test("conference/year changes abort obsolete requests and late data cannot replace results", async () => {
  const cache = new QueryClient();
  let resolveOld!: (data: KnowledgePaperBrowseResponse) => void;
  let oldSignal: AbortSignal | undefined;
  const oldOptions = paperBrowseQueryOptions({ conference: "AAAI", year: 2026, limit: 20, offset: 0 }, {
    browsePapers: (_params, signal) => { oldSignal = signal; return new Promise((resolve) => { resolveOld = resolve; }); },
  } as KnowledgeClient);
  const observer = new QueryObserver(cache, oldOptions);
  const unsubscribe = observer.subscribe(() => undefined);
  unsubscribe();
  assert.equal(oldSignal?.aborted, true);
  const current: KnowledgePaperBrowseResponse = { results: [], total: 0, limit: 20, offset: 0 };
  const nextOptions = paperBrowseQueryOptions({ conference: "CVPR", year: 2025, limit: 20, offset: 0 }, { browsePapers: async () => current } as unknown as KnowledgeClient);
  await cache.fetchQuery(nextOptions);
  resolveOld({ ...current, total: 999 });
  await Promise.resolve();
  assert.equal(cache.getQueryData(oldOptions.queryKey), undefined);
  assert.deepEqual(cache.getQueryData(nextOptions.queryKey), current);
  cache.clear();
});

test("restoration keeps conference filters and isolates scroll by mode, year and page", () => {
  const records = new Map<string, string>();
  const storage = { getItem: (key: string) => records.get(key) ?? null, setItem: (key: string, value: string) => { records.set(key, value); }, removeItem: (key: string) => { records.delete(key); } };
  const href = buildPaperBrowseUrl("AAAI", 2022, 2);
  const restoration = createSearchRestoration(() => storage);
  restoration.record("user:a", href);
  assert.equal(restoration.getHref("user:a", "/knowledge/search"), href);
  saveSearchScroll(storage, href, 500, 100);
  assert.equal(readSearchScroll(storage, href, 200), 500);
  assert.equal(readSearchScroll(storage, buildPaperBrowseUrl("AAAI", 2026, 2), 200), null);
  assert.equal(readSearchScroll(storage, buildPaperBrowseUrl("AAAI", 2022, 1), 200), null);
  assert.equal(readSearchScroll(storage, "/knowledge/search?q=graph&page=2", 200), null);
});

import assert from "node:assert/strict";
import test from "node:test";
import { BffKnowledgeClient } from "../../clients/knowledge/bff";
import { KnowledgeClientError } from "../../clients/knowledge/client";
import { createRealScholarProvider } from "../../features/knowledge/scholars/real-provider";
import { createMockScholarProvider } from "../../features/knowledge/scholars/mock-provider";
import { parseScholarContract, scholarProfileSchema } from "../../clients/knowledge/scholar-profiles";
import { scholarPage } from "../../features/knowledge/scholars/url-state";
import { recentCitations, scholarAvatarSource } from "../../features/knowledge/scholars/presentation";
import { createSearchRestoration } from "../../lib/navigation/search-restoration";

const profile = { scholar_id: "openalex:A5000001524", name_en: "Marcela Degrangemtsac", name_zh: null,
  metrics: { paper_count: 0, citation_count: null }, avatar_path: null };
const envelope = (data: unknown) => new Response(JSON.stringify({ code: 0, data }), { headers: { "Content-Type": "application/json" } });
async function withFetch(fetcher: typeof fetch, run: () => Promise<void>) {
  const original = globalThis.fetch;
  globalThis.fetch = fetcher;
  try { await run(); } finally { globalThis.fetch = original; }
}

test("real provider uses same-origin product endpoints, Unicode query, page offset and opaque IDs", async () => {
  const seen: string[] = [];
  const controller = new AbortController();
  await withFetch(async (input, init) => {
    seen.push(String(input));
    assert.ok(init?.signal);
    if (seen.length === 1) return envelope({ items: [profile], limit: 20, offset: 20, total: null, has_more: false });
    if (seen.length === 2) return envelope(profile);
    return envelope({ items: [], limit: 20, offset: 0, total: 0 });
  }, async () => {
    const provider = createRealScholarProvider();
    assert.equal(provider.isDemo, false);
    assert.equal(provider.supportsBrowse, false);
    assert.notEqual(provider.cacheKey, createMockScholarProvider().cacheKey);
    const page = await provider.search(" 何恺明 ", controller.signal, { limit: 20, offset: 20 });
    assert.equal(page.items[0].metrics?.paper_count, 0);
    assert.equal(page.items[0].metrics?.citation_count, null);
    assert.equal(page.total, null);
    await provider.detail("author:legacy/何?%252F", controller.signal);
    assert.deepEqual((await provider.papers(profile.scholar_id, 20, 0, controller.signal)).items, []);
  });
  assert.equal(seen[0], "/api/v1/knowledge/scholar-profiles/search?q=%E4%BD%95%E6%81%BA%E6%98%8E&limit=20&offset=20");
  assert.equal(seen[1], "/api/v1/knowledge/scholar-profiles/author%3Alegacy%2F%E4%BD%95%3F%25252F");
  assert.equal(seen[2], "/api/v1/knowledge/scholar-profile-papers?scholarId=openalex%3AA5000001524&limit=20&offset=0");
});

test("real detail NOT_FOUND becomes null; service failures never become demo data", async () => {
  await withFetch(async () => new Response(JSON.stringify({ code: "NOT_FOUND", message: "不存在", retryable: false, requestId: "r" }), { status: 404 }), async () => {
    assert.equal(await createRealScholarProvider().detail("missing"), null);
  });
  await withFetch(async () => new Response(JSON.stringify({ code: "TIMEOUT", message: "请求超时", retryable: true, requestId: "r" }), { status: 504 }), async () => {
    await assert.rejects(createRealScholarProvider().detail("missing"), (error: unknown) => error instanceof KnowledgeClientError && error.code === "TIMEOUT" && error.retryable);
  });
});

test("malformed product responses and OpenAlex raw records fail validation", async () => {
  for (const data of [{ id: "A1", display_name: "Name" }, { ...profile, metrics: { paper_count: -1 } }, { ...profile, metrics: { citation_count: "0" } }]) {
    assert.throws(() => parseScholarContract(scholarProfileSchema, data), (error: unknown) => error instanceof KnowledgeClientError && error.code === "CONTRACT_VIOLATION");
  }
  await withFetch(async () => envelope({ items: [profile], limit: 20, offset: 0 }), async () => {
    await assert.rejects(new BffKnowledgeClient().searchScholarProfiles("Marcel"), { code: "CONTRACT_VIOLATION" });
  });
});

test("active cancellation remains AbortError and canceled requests do not start", async () => {
  const canceled = new AbortController(); canceled.abort();
  let requests = 0;
  await withFetch(async (_input, init) => {
    requests++;
    return new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(init.signal?.reason), { once: true }));
  }, async () => {
    await assert.rejects(createRealScholarProvider().search("x", canceled.signal), { name: "AbortError" });
    assert.equal(requests, 0);
    const active = new AbortController();
    const result = createRealScholarProvider().search("x", active.signal);
    await new Promise((resolve) => setTimeout(resolve, 0)); active.abort();
    await assert.rejects(result, { name: "AbortError" });
    assert.equal(requests, 1);
  });
});

test("network failure and TimeoutError are classified by the Knowledge client", async () => {
  await withFetch(async () => { throw new DOMException("timeout", "TimeoutError"); }, async () => {
    await assert.rejects(createRealScholarProvider().search("x"), (error: unknown) => error instanceof KnowledgeClientError && error.code === "TIMEOUT" && error.retryable);
  });
  await withFetch(async () => { throw new TypeError("Failed to fetch"); }, async () => {
    await assert.rejects(createRealScholarProvider().search("x"), (error: unknown) => error instanceof KnowledgeClientError && error.code === "UPSTREAM_UNAVAILABLE" && error.retryable);
  });
});

test("mock pagination is isolated and supports empty results", async () => {
  const mock = createMockScholarProvider(0);
  const first = await mock.search("", undefined, { limit: 2, offset: 0 });
  const second = await mock.search("", undefined, { limit: 2, offset: 2 });
  assert.equal(first.total, 6); assert.ok(first.has_more);
  assert.notEqual(first.items[0].scholar_id, second.items[0].scholar_id);
  assert.deepEqual((await mock.search("不存在")).items, []);
});

test("page parsing and search restoration retain page and query across detail navigation", () => {
  for (const value of [null, "0", "-1", "1.5", "Infinity", "abc"]) assert.equal(scholarPage(value), 1);
  assert.equal(scholarPage("3"), 3);
  const storage = new Map<string, string>();
  const restoration = createSearchRestoration(() => ({ getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => { storage.set(key, value); }, removeItem: (key) => { storage.delete(key); } }));
  const href = "/knowledge/scholars?q=Marcel&page=2";
  restoration.record("anonymous", href);
  assert.equal(restoration.getHref("anonymous", "/knowledge/scholars"), href);
});

test("citation display uses the latest five reported years without filling gaps or nulls", () => {
  assert.deepEqual(recentCitations([{ year: 2000, count: 0 }, { year: 2003, count: null }, { year: 2012, count: 5 }]), [{ year: 2000, count: 0 }, { year: 2012, count: 5 }]);
  assert.equal(recentCitations(Array.from({ length: 7 }, (_, i) => ({ year: 2030 + i, count: i })))[0].year, 2032);
});


test("avatar errors and absent or unsafe sources fall back without retry loops", () => {
  const src = "https://images.example/avatar.png";
  assert.equal(scholarAvatarSource(src), src);
  assert.equal(scholarAvatarSource(src, src), null);
  assert.equal(scholarAvatarSource(null), null);
  assert.equal(scholarAvatarSource("javascript:alert(1)"), null);
  assert.equal(scholarAvatarSource("/avatars/upstream-only.png"), null);
  assert.equal(scholarAvatarSource("/images/scholars/demo-avatar.svg"), "/images/scholars/demo-avatar.svg");
});

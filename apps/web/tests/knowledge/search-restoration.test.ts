import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  createSearchRestoration,
  normalizeSearchRestorationHref,
  SEARCH_RESTORATION_ROUTES,
} from "../../lib/navigation/search-restoration";
import { readKnowledgeSearchUrlState } from "../../features/knowledge/search/search-url-state";
import { readTopicViewState } from "../../features/knowledge/topics/topic-url-state";
import { readFundingUrlState } from "../../features/knowledge/funding/funding-url-state";
import { paperHref } from "../../lib/navigation/paper";

function fixture() {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
  return { values, storage, restoration: createSearchRestoration(() => storage) };
}

const scope = "user:alice";
const paperPath = "/knowledge/search";
const paperSearch = `${paperPath}?q=Transformer&page=3&venue=AAAI&venue=ICRA&author=A&author=B&keyword=x&keyword=y`;

test("sidebar return restores query, page and repeated filters without losing values", () => {
  const { restoration } = fixture();
  restoration.record(scope, paperSearch);
  restoration.record(scope, "/projects");
  const href = restoration.getHref(scope, paperPath);
  assert.equal(href, paperSearch);
  const state = readKnowledgeSearchUrlState(new URL(href, "https://local.test").searchParams);
  assert.equal(state.query, "Transformer");
  assert.equal(state.page, 3);
  assert.deepEqual(state.filters.venue, ["AAAI", "ICRA"]);
  assert.deepEqual(state.filters.author, ["A", "B"]);
  assert.deepEqual(state.filters.keyword, ["x", "y"]);
  restoration.record(scope, paperSearch.replace("page=3", "page=4"));
  assert.equal(restoration.getHref(scope, paperPath), paperSearch.replace("page=3", "page=4"));
});

test("all four registered routes save independently and retain their Feature URL state", () => {
  const { restoration } = fixture();
  const searches = [paperSearch, "/knowledge/scholars?q=Hinton", "/knowledge/topics?q=llm&category=AI", "/knowledge/funding?q=NSF&funding=grant-1"];
  for (const href of searches) restoration.record(scope, href);
  assert.equal(Object.keys(SEARCH_RESTORATION_ROUTES).length, 4);
  for (const href of searches) assert.equal(restoration.getHref(scope, href.split("?")[0]), href);
  assert.deepEqual(readTopicViewState(new URLSearchParams(searches[2].split("?")[1])), { query: "llm", category: "AI" });
  assert.deepEqual(readFundingUrlState(new URLSearchParams(searches[3].split("?")[1])), { query: "NSF", fundingId: "grant-1" });
  restoration.clear(scope, "/knowledge/scholars");
  assert.equal(restoration.getHref(scope, "/knowledge/scholars"), "/knowledge/scholars");
  assert.equal(restoration.getHref(scope, paperPath), paperSearch);
});

test("refresh reads the same session record; direct parameter URLs remain authoritative", () => {
  const { restoration, storage } = fixture();
  restoration.record(scope, paperSearch);
  const refreshed = createSearchRestoration(() => storage);
  assert.equal(refreshed.getHref(scope, paperPath), paperSearch);
  const sharedLink = `${paperPath}?q=Diffusion&page=2&theme=dark`;
  assert.equal(refreshed.getHref(scope, sharedLink), sharedLink);
  refreshed.record(scope, sharedLink);
  assert.equal(refreshed.getHref(scope, paperPath), `${paperPath}?q=Diffusion&page=2`);
});

test("direct bare visits and empty/unknown parameters preserve records; explicit clear removes them", () => {
  const { restoration } = fixture();
  restoration.record(scope, paperSearch);
  for (const href of [paperPath, `${paperPath}?q=+&theme=dark`, "/"]) restoration.record(scope, href);
  assert.equal(restoration.getHref(scope, paperPath), paperSearch);
  restoration.clear(scope, paperPath);
  assert.equal(restoration.getHref(scope, paperPath), paperPath);
  restoration.record(scope, paperPath);
  assert.equal(restoration.getHref(scope, paperPath), paperPath);
});

test("browser history observations replace only the saved navigation target, not history", () => {
  const { restoration } = fixture();
  const first = `${paperPath}?q=first&page=1`;
  const second = `${paperPath}?q=second&page=2`;
  for (const href of [first, second, "/projects", second, first, second]) {
    restoration.record(scope, href);
    if (href !== "/projects") assert.equal(restoration.getHref(scope, paperPath), href);
  }
});

test("clear before auth resolves is applied to the resolved identity even after leaving the page", () => {
  const { restoration, storage } = fixture();
  restoration.record(scope, paperSearch);
  const refreshed = createSearchRestoration(() => storage);
  refreshed.clear(null, paperPath);
  refreshed.record(scope, "/knowledge/scholars");
  assert.equal(refreshed.getHref(scope, paperPath), paperPath);
});

test("paper detail returnTo preserves the complete URL and does not overwrite search restoration", () => {
  const { restoration } = fixture();
  restoration.record(scope, paperSearch);
  const detail = paperHref("paper/1", { mode: "create", source: paperSearch });
  restoration.record(scope, detail);
  assert.equal(new URL(detail, "https://local.test").searchParams.get("returnTo"), paperSearch);
  assert.equal(restoration.getHref(scope, paperPath), paperSearch);
});

test("only exact internal search paths and allowlisted nonempty parameters can be stored", () => {
  for (const href of [
    "https://evil.test/knowledge/search?q=x", "//evil.test/knowledge/search?q=x",
    "javascript:alert(1)", "/\\evil.test/knowledge/search?q=x", " /knowledge/search?q=x",
    "/knowledge/search\n?q=x", "/knowledge/%73earch?q=x", "/knowledge/topics/../search?q=x",
    "/knowledge/search/1?q=x", "/knowledge/search-extra?q=x", "/knowledge/search?q=x#fragment",
    "/unknown?q=x", "/__proto__?q=x", null,
  ]) assert.equal(normalizeSearchRestorationHref(href), null, String(href));
  assert.equal(normalizeSearchRestorationHref(`${paperPath}?q=x&returnTo=https%3A%2F%2Fevil.test&theme=dark&venue=A&venue=B`), `${paperPath}?q=x&venue=A&venue=B`);
  // Business value validation still belongs to the existing Feature parser.
  const invalidPage = normalizeSearchRestorationHref(`${paperPath}?q=x&page=-2&yearFrom=recent`)!;
  const state = readKnowledgeSearchUrlState(new URL(invalidPage, "https://local.test").searchParams);
  assert.equal(state.page, 1);
  assert.equal(state.filters.yearFrom, null);
});

test("corrupt or cross-route stored values safely fall back to the bare entry", () => {
  const { restoration, values } = fixture();
  restoration.record(scope, paperSearch);
  const key = [...values.keys()][0];
  for (const value of ["broken", "//evil.test", "/knowledge/scholars?q=other", `${paperPath}?returnTo=evil`]) {
    values.set(key, value);
    assert.equal(restoration.getHref(scope, paperPath), paperPath);
  }
});

test("identity scopes are isolated, including the URL left open during account switching", () => {
  const { restoration } = fixture();
  restoration.record("anonymous", `${paperPath}?q=guest`);
  restoration.record(scope, `${paperPath}?q=guest`); // Login while URL remains open.
  assert.equal(restoration.getHref(scope, paperPath), paperPath);
  restoration.record(scope, paperSearch);
  restoration.record("user:bob", paperSearch); // Switch without a URL change.
  assert.equal(restoration.getHref("user:bob", paperPath), paperPath);
  restoration.record("user:bob", paperSearch); // A shell remount still must not copy it.
  assert.equal(restoration.getHref("user:bob", paperPath), paperPath);
  restoration.record("user:bob", `${paperPath}?q=Bob`);
  assert.equal(restoration.getHref("user:bob", paperPath), `${paperPath}?q=Bob`);
  assert.equal(restoration.getHref(scope, paperPath), paperSearch);
  restoration.clear("user:bob", paperPath);
  assert.equal(restoration.getHref(scope, paperPath), paperSearch);
  assert.equal(restoration.getHref("anonymous", paperPath), `${paperPath}?q=guest`);
  assert.equal(restoration.getHref(null, paperPath), paperPath);
});

test("unavailable storage and throwing getters/reads/writes/clears never break navigation", () => {
  const fail = () => { throw new Error("Storage denied"); };
  for (const getStorage of [
    () => null, fail,
    () => ({ getItem: fail, setItem: fail, removeItem: fail }),
  ]) {
    const restoration = createSearchRestoration(getStorage);
    assert.doesNotThrow(() => restoration.record(scope, paperSearch));
    assert.doesNotThrow(() => restoration.clear(scope, paperPath));
    assert.equal(restoration.getHref(scope, paperPath), paperPath);
    assert.equal(restoration.getHref(scope, paperSearch), paperSearch);
    assert.equal(restoration.getHref(scope, "/projects"), "/projects");
  }
  const { restoration, storage } = fixture();
  restoration.record(scope, paperSearch);
  storage.removeItem = fail;
  restoration.clear(scope, paperPath);
  assert.equal(restoration.getHref(scope, paperPath), paperPath);
});

test("save and clear notify mounted links; unsubscribe removes the listener", () => {
  const { restoration } = fixture();
  let notified = 0;
  const unsubscribe = restoration.subscribe(() => { notified++; });
  restoration.record(scope, paperSearch);
  restoration.clear(scope, paperPath);
  assert.equal(notified, 2);
  unsubscribe();
  restoration.record(scope, paperSearch);
  assert.equal(notified, 2);
});

test("shell records under Suspense, opt-in links retain Link behavior, and Features explicitly clear", () => {
  const source = (path: string) => readFileSync(path, "utf8");
  assert.match(source("components/common/layout/app-shell.tsx"), /<Suspense fallback=\{null\}>\s*<SearchNavigationRecorder/);
  const sidebar = source("components/common/layout/app-sidebar.tsx");
  assert.match(sidebar, /Object.hasOwn\(SEARCH_RESTORATION_ROUTES, sub.href\)\s*\? SearchNavigationLink\s*: FeatureNavigationLink/);
  assert.match(sidebar, /<NavigationLink[\s\S]*?href=\{sub.href\}/);
  const link = source("components/common/layout/search-navigation-link.tsx");
  assert.match(link, /<FeatureNavigationLink \{\.\.\.props\} href=\{restoredHref\}/);
  assert.doesNotMatch(link, /router\.push|preventDefault/);
  const hook = source("hooks/use-search-restoration.ts");
  assert.match(hook, /useSyncExternalStore\(searchRestoration.subscribe, snapshot, \(\) => href\)/);
  assert.doesNotMatch(hook, /router|sessionStorage/);
  for (const path of [
    "features/knowledge/search/KnowledgeSearchPage.tsx",
    "features/knowledge/scholars/components/scholars-browser.tsx",
    "features/knowledge/topics/TopicsPage.tsx",
    "features/knowledge/funding/components/funding-browser.tsx",
  ]) assert.match(source(path), /clearRestoration\(\)/);
});

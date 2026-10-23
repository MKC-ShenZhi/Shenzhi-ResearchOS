import assert from "node:assert/strict";
import test from "node:test";
import type { KnowledgeConference } from "../../clients/knowledge/types";
import {
  normalizeConferenceBrowse,
  updateConferenceBrowse,
  type BrowseNavigationBrowser,
} from "../../features/knowledge/search/conferences/conference-navigation";

const ORIGIN = "https://local.test";
const ITEMS: KnowledgeConference[] = [
  { name: "AAAI", paperCount: 180, years: [2026, 2022, 2021, 2019], yearCount: 4 },
  { name: "ICML", paperCount: 90, years: [2025, 2024], yearCount: 2 },
];
const browse = (conference: string, year: number, page = 1) =>
  `/knowledge/search?mode=conference&conference=${conference}&year=${year}${page > 1 ? `&page=${page}` : ""}`;

/** Every location read sees the latest History write, without a React render. */
function memoryBrowser(initialHref: string) {
  const entries = [new URL(initialHref, ORIGIN)];
  const writes: Array<{ method: "push" | "replace"; href: string }> = [];
  let position = 0;
  const current = () => entries[position];
  const href = () => `${current().pathname}${current().search}${current().hash}`;
  const browser: BrowseNavigationBrowser = {
    location: {
      get pathname() { return current().pathname; },
      get search() { return current().search; },
      get hash() { return current().hash; },
    },
    history: {
      pushState(_data: unknown, _unused: string, next?: string | URL | null) {
        const destination = new URL(next == null ? current().href : String(next), current());
        entries.splice(position + 1);
        entries.push(destination);
        position++;
        writes.push({ method: "push", href: href() });
      },
      replaceState(_data: unknown, _unused: string, next?: string | URL | null) {
        entries[position] = new URL(next == null ? current().href : String(next), current());
        writes.push({ method: "replace", href: href() });
      },
    },
  };
  return {
    browser, writes,
    get href() { return href(); },
    get length() { return entries.length; },
    back() { if (position > 0) position--; },
    forward() { if (position + 1 < entries.length) position++; },
  };
}

test("rapid conference, year and page updates use the latest URL without rendering", () => {
  const navigation = memoryBrowser(browse("AAAI", 2019, 2));
  updateConferenceBrowse(ITEMS, { conference: "ICML" }, navigation.browser);
  updateConferenceBrowse(ITEMS, { year: 2024 }, navigation.browser);
  updateConferenceBrowse(ITEMS, { page: 3 }, navigation.browser);
  assert.equal(navigation.href, browse("ICML", 2024, 3));
  assert.deepEqual(navigation.writes, [
    { method: "push", href: browse("ICML", 2025) },
    { method: "push", href: browse("ICML", 2024) },
    { method: "push", href: browse("ICML", 2024, 3) },
  ]);
});

test("a stale year button cannot switch back to the previous conference", () => {
  const navigation = memoryBrowser(browse("AAAI", 2019));
  updateConferenceBrowse(ITEMS, { conference: "ICML" }, navigation.browser);
  updateConferenceBrowse(ITEMS, { year: 2022 }, navigation.browser);
  assert.equal(navigation.href, browse("ICML", 2025));
  assert.equal(navigation.writes.length, 1);
});

test("normalization reads the current URL and cannot overwrite a newer conference", () => {
  const navigation = memoryBrowser("/knowledge/search?mode=conference&conference=AAAI&year=1999&page=3");
  updateConferenceBrowse(ITEMS, { conference: "ICML" }, navigation.browser);
  // This models a normalization effect queued before the user's selection.
  normalizeConferenceBrowse(ITEMS, navigation.browser);
  assert.equal(navigation.href, browse("ICML", 2025));
  assert.deepEqual(navigation.writes, [{ method: "push", href: browse("ICML", 2025) }]);
});

test("missing or invalid years replace the current entry and reset pagination", () => {
  for (const initial of [
    "/knowledge/search",
    "/knowledge/search?mode=conference&page=4",
    "/knowledge/search?mode=conference&conference=AAAI&page=4",
    "/knowledge/search?mode=conference&conference=AAAI&year=1999&page=4",
    "/knowledge/search?mode=conference&conference=AAAI&year=invalid&page=4",
  ]) {
    const navigation = memoryBrowser(initial);
    normalizeConferenceBrowse(ITEMS, navigation.browser);
    normalizeConferenceBrowse(ITEMS, navigation.browser);
    assert.equal(navigation.href, browse("AAAI", 2026), initial);
    assert.equal(navigation.length, 1, initial);
    assert.deepEqual(navigation.writes, [{ method: "replace", href: browse("AAAI", 2026) }], initial);
  }
});

test("repeating an unchanged selection does not create duplicate history", () => {
  const navigation = memoryBrowser(browse("AAAI", 2026));
  updateConferenceBrowse(ITEMS, { conference: "AAAI" }, navigation.browser);
  updateConferenceBrowse(ITEMS, { year: 2026 }, navigation.browser);
  updateConferenceBrowse(ITEMS, { page: 1 }, navigation.browser);
  normalizeConferenceBrowse(ITEMS, navigation.browser);
  assert.equal(navigation.length, 1);
  assert.deepEqual(navigation.writes, []);
});

test("unknown conferences stay explicit until the user chooses a known conference", () => {
  const initial = "/knowledge/search?mode=conference&conference=UNKNOWN&year=2022&page=3";
  const navigation = memoryBrowser(initial);
  normalizeConferenceBrowse(ITEMS, navigation.browser);
  updateConferenceBrowse(ITEMS, { year: 2021 }, navigation.browser);
  updateConferenceBrowse(ITEMS, { page: 2 }, navigation.browser);
  updateConferenceBrowse(ITEMS, { conference: "ALSO_UNKNOWN" }, navigation.browser);
  assert.equal(navigation.href, initial);
  assert.deepEqual(navigation.writes, []);
  updateConferenceBrowse(ITEMS, { conference: "ICML" }, navigation.browser);
  assert.equal(navigation.href, browse("ICML", 2025));
});

test("empty conference metadata leaves the URL untouched", () => {
  const navigation = memoryBrowser(browse("AAAI", 2026));
  normalizeConferenceBrowse([], navigation.browser);
  updateConferenceBrowse([], { conference: "ICML" }, navigation.browser);
  updateConferenceBrowse([], { year: 2022 }, navigation.browser);
  assert.equal(navigation.href, browse("AAAI", 2026));
  assert.deepEqual(navigation.writes, []);
});

test("stale conference handlers cannot overwrite keyword mode or another page", () => {
  for (const initial of [
    "/knowledge/search?mode=keyword&q=diffusion&page=2",
    "/knowledge/search?q=diffusion&page=2",
    "/knowledge/search?mode=keyword&conference=AAAI&year=2026",
    "/knowledge/search/conferences?year=2022",
    "/papers/fixture-paper?returnTo=%2Fknowledge%2Fsearch",
  ]) {
    const navigation = memoryBrowser(initial);
    normalizeConferenceBrowse(ITEMS, navigation.browser);
    updateConferenceBrowse(ITEMS, { conference: "ICML" }, navigation.browser);
    updateConferenceBrowse(ITEMS, { year: 2024 }, navigation.browser);
    updateConferenceBrowse(ITEMS, { page: 2 }, navigation.browser);
    assert.equal(navigation.href, initial);
    assert.deepEqual(navigation.writes, [], initial);
  }
});

test("browser back and forward retain selections and new actions replace the forward branch", () => {
  const navigation = memoryBrowser(browse("AAAI", 2026));
  updateConferenceBrowse(ITEMS, { year: 2022 }, navigation.browser);
  updateConferenceBrowse(ITEMS, { conference: "ICML" }, navigation.browser);
  updateConferenceBrowse(ITEMS, { page: 2 }, navigation.browser);
  navigation.back();
  assert.equal(navigation.href, browse("ICML", 2025));
  navigation.back();
  assert.equal(navigation.href, browse("AAAI", 2022));
  navigation.forward();
  assert.equal(navigation.href, browse("ICML", 2025));
  updateConferenceBrowse(ITEMS, { year: 2024 }, navigation.browser);
  navigation.forward();
  assert.equal(navigation.href, browse("ICML", 2024));
  navigation.back();
  assert.equal(navigation.href, browse("ICML", 2025));
});

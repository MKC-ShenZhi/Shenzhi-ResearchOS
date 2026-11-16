import assert from "node:assert/strict";
import test from "node:test";
import { createSearchDrafts } from "../../lib/navigation/search-draft";

function fixture() {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
  let time = 1000;
  return { values, storage, now: () => time, advance: (ms: number) => { time += ms; } };
}

const scope = "user:alice";
const entry = "/knowledge/search";
const source = `${entry}?q=Transformer&page=3&venue=AAAI`;

test("unsubmitted text survives leaving, remounting and refreshing the same search context", () => {
  const { storage, now } = fixture();
  const drafts = createSearchDrafts(() => storage, now);
  drafts.set(scope, entry, source, "Transformer policies");
  assert.equal(drafts.get(scope, entry, source, "Transformer"), "Transformer policies");
  const refreshed = createSearchDrafts(() => storage, now);
  assert.equal(refreshed.get(scope, entry, source, "Transformer"), "Transformer policies");
  for (const explicit of ["?q=Diffusion", "?q=Transformer&page=1", "?q=Transformer&page=3&venue=ICRA", ""]) {
    assert.equal(refreshed.get(scope, entry, entry + explicit, "URL wins"), "URL wins");
  }
});

test("identity and entry isolation, logout and account switching clear outgoing drafts", () => {
  const { storage, now } = fixture();
  const drafts = createSearchDrafts(() => storage, now);
  drafts.activate(scope);
  drafts.set(scope, entry, source, "Alice draft");
  drafts.set(scope, "home-search", "", "home keyword");
  assert.equal(drafts.get(scope, "home-search", "", ""), "home keyword");
  assert.equal(drafts.get("anonymous", entry, source, ""), "");
  assert.equal(drafts.get("user:bob", entry, source, ""), "");
  assert.equal(drafts.get(null, entry, source, "URL"), "URL");
  drafts.activate("user:bob");
  assert.equal(drafts.get(scope, entry, source, ""), "");
  assert.equal(drafts.get(scope, "home-search", "", ""), "");
  drafts.set("user:bob", entry, source, "Bob draft");
  drafts.activate("anonymous");
  const refreshed = createSearchDrafts(() => storage, now);
  assert.equal(refreshed.get("user:bob", entry, source, ""), "");
});

test("empty draft is preserved until submit; submit/explicit clear restores committed URL value", () => {
  const { storage, now } = fixture();
  const drafts = createSearchDrafts(() => storage, now);
  drafts.set(scope, entry, source, "");
  assert.equal(drafts.get(scope, entry, source, "Transformer"), "");
  drafts.clear(scope, entry);
  assert.equal(drafts.get(scope, entry, source, "Transformer"), "Transformer");
  assert.equal(createSearchDrafts(() => storage, now).get(scope, entry, source, "Transformer"), "Transformer");
});

test("drafts expire after 30 minutes and corrupt/future/oversized records are ignored", () => {
  const { values, storage, now, advance } = fixture();
  const drafts = createSearchDrafts(() => storage, now);
  drafts.set(scope, entry, source, "draft");
  const key = [...values.keys()][0];
  advance(30 * 60 * 1000 + 1);
  assert.equal(drafts.get(scope, entry, source, "URL"), "URL");
  assert.equal(createSearchDrafts(() => storage, now).get(scope, entry, source, "URL"), "URL");
  for (const raw of ["{", "null", "[]", JSON.stringify({ source, value: "x", updatedAt: now() + 1 }), JSON.stringify({ source, value: "x".repeat(2001), updatedAt: now() })]) {
    values.set(key, raw);
    assert.equal(createSearchDrafts(() => storage, now).get(scope, entry, source, "URL"), "URL");
  }
});

test("blocked storage allows editing and clearing without reviving older text", () => {
  const fail = () => { throw new Error("storage denied"); };
  for (const getStorage of [() => null, fail, () => ({ getItem: fail, setItem: fail, removeItem: fail })]) {
    const drafts = createSearchDrafts(getStorage);
    drafts.set(scope, entry, source, "local draft");
    assert.equal(drafts.get(scope, entry, source, "URL"), "local draft");
    drafts.clear(scope, entry);
    assert.equal(drafts.get(scope, entry, source, "URL"), "URL");
  }
});

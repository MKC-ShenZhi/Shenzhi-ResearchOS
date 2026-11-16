import assert from "node:assert/strict";
import test from "node:test";
import { clearSearchScroll, readSearchScroll, saveSearchScroll } from "../../features/knowledge/search/search-scroll-state";

const source = "/knowledge/search?q=robotics&page=2&venue=RSS";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

test("paper search scroll is isolated by query, page and filters, and survives URL parameter reordering", () => {
  const storage = memoryStorage();
  saveSearchScroll(storage, source, 1234, 100);
  assert.equal(readSearchScroll(storage, source, 101), 1234);
  assert.equal(readSearchScroll(storage, "/knowledge/search?venue=RSS&page=2&q=robotics", 101), 1234);
  for (const other of [source.replace("robotics", "vision"), source.replace("page=2", "page=1"), source.replace("RSS", "ICRA")]) {
    assert.equal(readSearchScroll(storage, other, 101), null);
  }
  clearSearchScroll(storage, source);
  assert.equal(readSearchScroll(storage, source, 101), null);
});

test("invalid, corrupt, expired and future scroll records are ignored", () => {
  const storage = memoryStorage();
  saveSearchScroll(storage, source, 900, 100);
  assert.equal(readSearchScroll(storage, source, 100 + 30 * 60_000 + 1), null);
  assert.equal(storage.values.size, 0);
  for (const raw of ["{", "null", '{"top":-1,"savedAt":100}', '{"top":"900","savedAt":100}', '{"top":900,"savedAt":1000}']) {
    saveSearchScroll(storage, source, 900, 100);
    const key = [...storage.values.keys()][0];
    storage.setItem(key, raw);
    assert.equal(readSearchScroll(storage, source, 101), null);
    assert.equal(storage.values.size, 0);
  }
  saveSearchScroll(storage, source, NaN);
  saveSearchScroll(storage, source, Infinity);
  saveSearchScroll(storage, source, -1);
  assert.equal(storage.values.size, 0);
});

test("unavailable session storage does not break paper navigation", () => {
  const blocked = () => { throw new Error("SecurityError"); };
  const storage = { getItem: blocked, setItem: blocked, removeItem: blocked };
  assert.doesNotThrow(() => saveSearchScroll(storage, source, 100));
  assert.equal(readSearchScroll(storage, source), null);
  assert.doesNotThrow(() => clearSearchScroll(storage, source));
});


test("scroll records use the existing navigation identity scopes", () => {
  const storage = memoryStorage();
  saveSearchScroll(storage, source, 900, 100, "user:alice");
  saveSearchScroll(storage, source, 300, 100, "user:bob");
  assert.equal(readSearchScroll(storage, source, 101, "anonymous"), null);
  assert.equal(readSearchScroll(storage, source, 101, "user:alice"), 900);
  assert.equal(readSearchScroll(storage, source, 101, "user:bob"), 300);
  clearSearchScroll(storage, source, "user:bob");
  assert.equal(readSearchScroll(storage, source, 101, "user:bob"), null);
  assert.equal(readSearchScroll(storage, source, 101, "user:alice"), 900);
});

test("directory results and keyword results never share scroll even with identical query and page", () => {
  const storage = memoryStorage();
  const directory = "/knowledge/search/conferences?q=robotics&page=2&sort=name&year=2022";
  saveSearchScroll(storage, directory, 400, 100);
  saveSearchScroll(storage, source, 1200, 100);
  assert.equal(readSearchScroll(storage, directory, 101), 400);
  assert.equal(readSearchScroll(storage, source, 101), 1200);
  assert.equal(readSearchScroll(storage, directory.replace("2022", "2021"), 101), null);
  assert.equal(readSearchScroll(storage, directory.replace("name", "count"), 101), null);
  assert.equal(readSearchScroll(storage, directory.replace("page=2", "page=1"), 101), null);
  assert.equal(readSearchScroll(storage, "/knowledge/search?q=robotics&page=2", 101), null);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildKnowledgeSearchUrl,
  readKnowledgeSearchUrlState,
} from "../../features/knowledge/search/search-url-state";

test("paper search restores query, filters and page from the URL", () => {
  const params = new URLSearchParams(
    "q=diffusion+policy&page=4&yearFrom=2021&yearTo=2025" +
      "&venue=RSS&venue=ICRA&author=Cheng+Chi&keyword=robotics" +
      "&subject=Computer+Science",
  );

  assert.deepEqual(readKnowledgeSearchUrlState(params), {
    query: "diffusion policy",
    page: 4,
    filters: {
      yearFrom: 2021,
      yearTo: 2025,
      venue: ["RSS", "ICRA"],
      author: ["Cheng Chi"],
      keyword: ["robotics"],
      subject: ["Computer Science"],
    },
  });
});

test("paper search serializes all result-affecting state into a recoverable URL", () => {
  const url = buildKnowledgeSearchUrl({
    query: "diffusion policy",
    page: 3,
    filters: {
      yearFrom: 2022,
      yearTo: null,
      venue: ["RSS", "ICRA"],
      author: ["Cheng Chi"],
      keyword: ["robotics"],
      subject: ["Computer Science"],
    },
  });
  const parsed = new URL(url, "https://local.test");

  assert.equal(parsed.pathname, "/knowledge/search");
  assert.deepEqual(readKnowledgeSearchUrlState(parsed.searchParams), {
    query: "diffusion policy",
    page: 3,
    filters: {
      yearFrom: 2022,
      yearTo: null,
      venue: ["RSS", "ICRA"],
      author: ["Cheng Chi"],
      keyword: ["robotics"],
      subject: ["Computer Science"],
    },
  });
});

test("paper search normalizes invalid URL pagination and years", () => {
  const state = readKnowledgeSearchUrlState(
    new URLSearchParams("q=robotics&page=-2&yearFrom=recent&yearTo=2025.5"),
  );

  assert.equal(state.page, 1);
  assert.equal(state.filters.yearFrom, null);
  assert.equal(state.filters.yearTo, null);
});

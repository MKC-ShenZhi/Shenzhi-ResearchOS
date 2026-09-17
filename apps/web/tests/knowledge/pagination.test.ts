import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  KNOWLEDGE_SEARCH_PAGE_SIZE,
  knowledgePaginationItems,
  knowledgeSearchOffset,
} from "../../features/knowledge/search/pagination.js";

const PAGE_SOURCE = readFileSync(
  "features/knowledge/search/KnowledgeSearchPage.tsx",
  "utf8",
);
const RESULTS_SOURCE = readFileSync(
  "features/knowledge/search/components/results-section.tsx",
  "utf8",
);

test("paper-search pages use a fixed size of 20 and request their own offsets", () => {
  assert.equal(KNOWLEDGE_SEARCH_PAGE_SIZE, 20);
  assert.equal(knowledgeSearchOffset(1), 0);
  assert.equal(knowledgeSearchOffset(2), 20);
  assert.equal(knowledgeSearchOffset(3), 40);
  assert.match(PAGE_SOURCE, /offset:\s*knowledgeSearchOffset\(page\)/);
  assert.doesNotMatch(RESULTS_SOURCE, /results\.slice/);
});

test("pagination exposes page numbers and only a verified look-ahead page", () => {
  assert.deepEqual(knowledgePaginationItems(1, true), [1, 2]);
  assert.deepEqual(knowledgePaginationItems(2, true), [1, 2, 3]);
  assert.deepEqual(knowledgePaginationItems(4, true), [1, "ellipsis", 3, 4, 5]);
  assert.deepEqual(knowledgePaginationItems(4, false), [1, "ellipsis", 3, 4]);
});

test("submitting another query or changing filters resets paper search to page one", () => {
  const submitSearch = PAGE_SOURCE.match(
    /const submitSearch = \(q: string\) => \{([\s\S]*?)\n\s*\};/,
  )?.[1] ?? "";
  const updateFilters = PAGE_SOURCE.match(
    /const updateFilters = \(nextFilters: KnowledgeFilters\) => \{([\s\S]*?)\n\s*\};/,
  )?.[1] ?? "";

  assert.match(submitSearch, /setCommittedQuery\(text\);[\s\S]*setPage\(1\)/);
  assert.match(updateFilters, /setFilters\(nextFilters\);[\s\S]*setPage\(1\)/);
  assert.match(PAGE_SOURCE, /onChange=\{updateFilters\}/);
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const COMPOSER_SOURCE = readFileSync("components/common/composer/composer.tsx", "utf8");
const SEARCH_HERO_SOURCE = readFileSync("features/search/components/search-hero.tsx", "utf8");
const KNOWLEDGE_PAGE_SOURCE = readFileSync("features/knowledge/search/KnowledgeSearchPage.tsx", "utf8");
const RESULTS_SOURCE = readFileSync("features/knowledge/search/components/results-section.tsx", "utf8");
const QUERY_HOOK_SOURCE = readFileSync("features/knowledge/search/use-knowledge-search.ts", "utf8");
const QUERY_RESOURCE_SOURCE = readFileSync("features/knowledge/search/search-query-resource.ts", "utf8");
const RESULT_CARD_SOURCE = readFileSync("features/knowledge/search/components/result-card.tsx", "utf8");
const SEARCH_ROUTE_SOURCE = readFileSync("app/search/page.tsx", "utf8");

test("simple search submit goes to the formal Knowledge paper-search route", () => {
  assert.match(
    SEARCH_HERO_SOURCE,
    /if \(payload\.entryMode === "search"\)[\s\S]*?router\.push\(`\/knowledge\/search\?q=\$\{encodeURIComponent\(payload\.question\)\}`\)/,
  );
  assert.match(SEARCH_ROUTE_SOURCE, /redirect/);
});

test("simple search does not render an inline duplicate result journey", () => {
  assert.doesNotMatch(SEARCH_HERO_SOURCE, /setInlineSearch|<SearchResults/);
});

test("formal simple search uses Knowledge retrieval and paper result states", () => {
  assert.match(RESULTS_SOURCE, /useKnowledgeSearch\(params\)/);
  assert.match(QUERY_HOOK_SOURCE, /useQuery\(knowledgeSearchQueryOptions\(normalizedParams\)\)/);
  assert.match(QUERY_RESOURCE_SOURCE, /client\.search\(normalizedParams, signal\)/);
  assert.doesNotMatch(RESULTS_SOURCE, /ModelProvider|chatInputFromComposer|createChatSession|\bsend\(/);
  assert.match(QUERY_RESOURCE_SOURCE, /queryKey: knowledgeSearchQueryKey/);
  assert.match(KNOWLEDGE_PAGE_SOURCE, /if \(!normalizedQuery\) return null/);
  assert.match(RESULTS_SOURCE, /KnowledgeSearchSkeleton/);
  assert.match(RESULTS_SOURCE, /KnowledgeSearchError/);
  assert.match(RESULTS_SOURCE, /KnowledgeSearchEmpty/);
  assert.match(RESULTS_SOURCE, /KnowledgeResultCard/);
  assert.match(RESULTS_SOURCE, /KnowledgeClientError/);
  assert.match(QUERY_RESOURCE_SOURCE, /retry:\s*knowledgeQueryRetry/);
  assert.match(KNOWLEDGE_PAGE_SOURCE, /KnowledgeResultsSection/);
  assert.match(KNOWLEDGE_PAGE_SOURCE, /KnowledgeFilterPanel/);
  assert.match(
    RESULT_CARD_SOURCE,
    /const detailHref = paperHref\(hit\.id, \{ mode: "create", source: returnTo \}\)/,
  );
  assert.match(RESULT_CARD_SOURCE, /href=\{detailHref\}/);
  assert.doesNotMatch(RESULTS_SOURCE, /深知 AI|思考完成|Reasoning|ModelProvider|引用 \[\d+\]/);
});

test("simple and smart mode state remains a single Composer contract", () => {
  assert.match(COMPOSER_SOURCE, /简单搜索/);
  assert.match(COMPOSER_SOURCE, /智能搜索/);
  assert.match(COMPOSER_SOURCE, /onEntryModeChange/);
});

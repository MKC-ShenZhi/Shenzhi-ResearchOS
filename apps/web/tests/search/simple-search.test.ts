import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const AGENT_CHAT_SOURCE = readFileSync("features/chat/components/agent-chat.tsx", "utf8");
const COMPOSER_SOURCE = readFileSync("features/chat/components/composer.tsx", "utf8");
const SEARCH_HERO_SOURCE = readFileSync("features/search/components/search-hero.tsx", "utf8");
const KNOWLEDGE_PAGE_SOURCE = readFileSync("features/knowledge/search/KnowledgeSearchPage.tsx", "utf8");
const RESULTS_SOURCE = readFileSync("features/knowledge/search/components/results-section.tsx", "utf8");
const RESULT_CARD_SOURCE = readFileSync("features/knowledge/search/components/result-card.tsx", "utf8");
const SEARCH_ROUTE_SOURCE = readFileSync("app/search/page.tsx", "utf8");

test("simple search submit goes to the formal Knowledge paper-search route", () => {
  assert.match(
    AGENT_CHAT_SOURCE,
    /if \(payload\.entryMode === "search"\)[\s\S]*?router\.push\(`\/knowledge\/search\?q=\$\{encodeURIComponent\(payload\.question\)\}`\)/,
  );
  assert.match(
    SEARCH_HERO_SOURCE,
    /if \(payload\.entryMode === "search"\)[\s\S]*?router\.push\(`\/knowledge\/search\?q=\$\{encodeURIComponent\(payload\.question\)\}`\)/,
  );
  assert.match(SEARCH_ROUTE_SOURCE, /redirect/);
});

test("simple search does not render an inline duplicate result journey", () => {
  assert.doesNotMatch(SEARCH_HERO_SOURCE, /setInlineSearch|<SearchResults/);
});

test("simple search submit never enters Chat send or creates a Chat session", () => {
  const searchBranch = AGENT_CHAT_SOURCE.match(
    /if \(payload\.entryMode === "search"\) \{([\s\S]*?)\n\s*\}/,
  )?.[1] ?? "";
  assert.notEqual(searchBranch, "");
  assert.doesNotMatch(searchBranch, /chatInputFromComposer|\bsend\(|createChatSession/);
});

test("formal simple search uses Knowledge retrieval and paper result states", () => {
  assert.match(RESULTS_SOURCE, /getKnowledgeClient\(\)\.search/);
  assert.doesNotMatch(RESULTS_SOURCE, /ModelProvider|chatInputFromComposer|createChatSession|\bsend\(/);
  assert.match(RESULTS_SOURCE, /queryKey/);
  assert.match(RESULTS_SOURCE, /enabled:\s*query\.length\s*>\s*0/);
  assert.match(RESULTS_SOURCE, /KnowledgeSearchSkeleton/);
  assert.match(RESULTS_SOURCE, /KnowledgeSearchError/);
  assert.match(RESULTS_SOURCE, /KnowledgeSearchEmpty/);
  assert.match(RESULTS_SOURCE, /KnowledgeResultCard/);
  assert.match(RESULTS_SOURCE, /KnowledgeClientError/);
  assert.match(RESULTS_SOURCE, /retry:\s*knowledgeQueryRetry/);
  assert.match(KNOWLEDGE_PAGE_SOURCE, /KnowledgeResultsSection/);
  assert.match(KNOWLEDGE_PAGE_SOURCE, /KnowledgeFilterPanel/);
  assert.match(RESULT_CARD_SOURCE, /href=\{paperHref\(hit\.id, returnTo\)\}/);
  assert.doesNotMatch(RESULTS_SOURCE, /深知 AI|思考完成|Reasoning|ModelProvider|引用 \[\d+\]/);
});

test("simple and smart mode state remains a single Composer contract", () => {
  assert.match(COMPOSER_SOURCE, /简单搜索/);
  assert.match(COMPOSER_SOURCE, /智能搜索/);
  assert.match(COMPOSER_SOURCE, /onEntryModeChange/);
  assert.match(AGENT_CHAT_SOURCE, /entryMode=\{entryMode\}/);
  assert.match(AGENT_CHAT_SOURCE, /onEntryModeChange=\{setEntryMode\}/);
  assert.doesNotMatch(AGENT_CHAT_SOURCE, /<SearchResults|setInlineSearch/);
});

test("smart search keeps the Knowledge2Chat adapter and Chat send path", () => {
  assert.match(AGENT_CHAT_SOURCE, /const request = chatInputFromComposer\(payload\)/);
  assert.match(AGENT_CHAT_SOURCE, /void send\(request\)/);
  assert.match(AGENT_CHAT_SOURCE, /setEntryMode\(payload\.entryMode\)/);
  assert.match(AGENT_CHAT_SOURCE, /capabilitiesForEntryMode\("ai"\)/);
});

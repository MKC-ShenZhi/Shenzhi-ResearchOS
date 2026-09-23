import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebar = readFileSync("components/common/layout/app-sidebar.tsx", "utf8");
const knowledgeLayout = readFileSync("app/knowledge/layout.tsx", "utf8");
const scholarDetailRoute = readFileSync(
  "app/knowledge/scholars/[scholarId]/page.tsx",
  "utf8",
);
const dashboard = readFileSync(
  "features/knowledge/components/knowledge-dashboard.tsx",
  "utf8",
);
const scholarBrowser = readFileSync(
  "features/knowledge/scholars/components/scholars-browser.tsx",
  "utf8",
);
const fundingPage = readFileSync("features/knowledge/funding/FundingPage.tsx", "utf8");
const relatedSearch = readFileSync(
  "features/knowledge/components/related-paper-search.tsx",
  "utf8",
);

test("Knowledge sidebar exposes exactly the six V1 capability entries", () => {
  const block = sidebar.match(/const KNOWLEDGE_SUB_NAV = \[([\s\S]*?)\];/)?.[1] ?? "";
  const labels = [...block.matchAll(/label: "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(labels, [
    "论文库",
    "我的文献",
    "学者库",
    "主题库",
    "项目专利基金库",
    "关系图谱",
  ]);
  assert.doesNotMatch(block, /专利库|研究机构/);
});

test("Knowledge uses one shared shell and parent navigation returns to overview", () => {
  assert.match(knowledgeLayout, /return <AppShell>\{children\}<\/AppShell>/);
  assert.doesNotMatch(scholarDetailRoute, /AppShell/);
  assert.match(
    sidebar,
    /if \(routeActive\) \{[\s\S]*?setCollapsed\(false\);[\s\S]*?setExpanded\(href, true\);[\s\S]*?router\.push\(href, \{ scroll: false \}\);/,
  );
});

test("Knowledge dashboard uses the real overview client and preserves capability routes", () => {
  assert.doesNotMatch(dashboard, /data-(scholars|funding|patents|institutions|library)/);
  assert.match(dashboard, /overviewSearch/);
  assert.match(dashboard, /跨库检索/);
  assert.match(dashboard, /项目专利基金/);
  assert.match(dashboard, /资产信息/);
  assert.match(dashboard, /highlights/);
  assert.match(dashboard, /暂无可展示的真实基金资产信息/);
  for (const href of [
    "/knowledge/search",
    "/knowledge/papers",
    "/knowledge/scholars",
    "/knowledge/topics",
    "/knowledge/funding",
    "/knowledge/graph",
  ]) {
    assert.match(dashboard, new RegExp(href));
  }
});

test("formal Scholar and Funding paths no longer import prototype entity data", () => {
  assert.doesNotMatch(scholarBrowser, /data-scholars/);
  assert.match(scholarBrowser, /searchScholars/);
  assert.doesNotMatch(fundingPage, /funding-browser|data-funding/);
  assert.match(fundingPage, /kind="funding"/);
});

test("Topic and Funding share the real paper result presentation", () => {
  assert.match(relatedSearch, /searchBySubject/);
  assert.match(relatedSearch, /searchByFunding/);
  assert.match(relatedSearch, /KnowledgeResultCard/);
  assert.match(relatedSearch, /KnowledgeSearchSkeleton/);
  assert.match(relatedSearch, /KnowledgeSearchError/);
  assert.match(relatedSearch, /KnowledgeSearchEmpty/);
});

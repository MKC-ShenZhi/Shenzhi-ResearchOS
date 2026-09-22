import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebar = readFileSync("components/common/layout/app-sidebar.tsx", "utf8");
const dashboard = readFileSync(
  "features/knowledge/components/knowledge-dashboard.tsx",
  "utf8",
);
const scholarBrowser = readFileSync(
  "features/knowledge/scholars/components/scholars-browser.tsx",
  "utf8",
);
const fundingPage = readFileSync("features/knowledge/funding/FundingPage.tsx", "utf8");
const fundingBrowser = readFileSync(
  "features/knowledge/funding/components/funding-browser.tsx",
  "utf8",
);
const fundingUrlState = readFileSync(
  "features/knowledge/funding/funding-url-state.ts",
  "utf8",
);
const patentsPage = readFileSync("features/knowledge/patents/PatentsPage.tsx", "utf8");
const commonAttachmentMenu = readFileSync(
  "components/common/composer/attachment-menu.tsx",
  "utf8",
);
const chatAttachmentMenu = readFileSync(
  "features/chat/components/attachment-menu.tsx",
  "utf8",
);
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
    "项目基金库",
    "关系图谱",
  ]);
  assert.doesNotMatch(block, /专利库|研究机构/);
});

test("Knowledge dashboard is capability-only and does not import prototype data", () => {
  assert.doesNotMatch(dashboard, /data-(scholars|funding|patents|institutions|library)/);
  assert.doesNotMatch(dashboard, /跨库检索|专利记录|关注学者/);
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
  assert.doesNotMatch(fundingPage, /data-funding|RelatedPaperSearch/);
  assert.match(fundingPage, /FundingBrowser/);
});

test("Funding page uses candidate search without legacy entity fields", () => {
  assert.match(fundingBrowser, /searchFundings/);
  assert.match(fundingBrowser, /searchByFunding/);
  assert.match(fundingBrowser, /\.name/);
  assert.match(fundingBrowser, /results\.length < /);
  assert.doesNotMatch(fundingBrowser, /grantNo|pi|institution|amount|period|category|status/);
  assert.doesNotMatch(fundingPage, /data-funding|FundingTable|FundingPanel/);
});

test("Funding page uses the project-funding name and URL-backed selection state", () => {
  assert.match(fundingBrowser, /项目基金库/);
  assert.match(sidebar, /label: "项目基金库"/);
  assert.match(dashboard, /title: "项目基金库"/);
  assert.match(fundingBrowser, /useSearchParams/);
  assert.match(fundingBrowser, /readFundingUrlState/);
  assert.match(fundingUrlState, /searchParams\.get\("q"\)/);
  assert.match(fundingUrlState, /searchParams\.get\("funding"\)/);
  assert.match(fundingBrowser, /router\.replace/);
  assert.match(fundingBrowser, /fundingRestoreQuery/);
  assert.match(fundingBrowser, /query: fundingId!/);
  assert.match(fundingBrowser, /candidate\.id === fundingId/);
  assert.match(fundingBrowser, /key=\{searchParams\.toString\(\)\}/);
  assert.equal((fundingBrowser.match(/searchByFunding\(/g) ?? []).length, 1);
  assert.doesNotMatch(fundingBrowser, /relatedPaperQuery\.isPending \|\| relatedPaperQuery\.isFetching/);
});

test("Funding URL-dependent state is isolated and restoration failures stay visible", () => {
  assert.match(fundingPage, /Suspense/);
  assert.match(fundingBrowser, /fundingQuery\.isSuccess/);
  assert.match(fundingBrowser, /fundingRestoreQuery\.isError/);
});

test("Patent compatibility route is unavailable and does not render mock data", () => {
  assert.match(patentsPage, /暂未提供专利实体检索能力/);
  assert.doesNotMatch(patentsPage, /PatentsBrowser|data-patents/);
});

test("attachment menus do not expose unsupported Funding or Patent mock entities", () => {
  for (const source of [commonAttachmentMenu, chatAttachmentMenu]) {
    assert.doesNotMatch(source, /data-funding|data-patents|项目基金库|专利库/);
  }
});

test("Topic keeps the real paper result presentation", () => {
  assert.match(relatedSearch, /searchBySubject/);
  assert.match(relatedSearch, /KnowledgeResultCard/);
  assert.match(relatedSearch, /KnowledgeSearchSkeleton/);
  assert.match(relatedSearch, /KnowledgeSearchError/);
  assert.match(relatedSearch, /KnowledgeSearchEmpty/);
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { scholarHref, scholarIdFromRouteParam } from "../../lib/navigation/scholar";

const browser = readFileSync(
  "features/knowledge/scholars/components/scholars-browser.tsx",
  "utf8",
);
const card = readFileSync(
  "features/knowledge/scholars/components/scholar-card.tsx",
  "utf8",
);
const detail = readFileSync(
  "features/knowledge/scholars/ScholarDetailPage.tsx",
  "utf8",
);
const route = readFileSync(
  "app/knowledge/scholars/[scholarId]/page.tsx",
  "utf8",
);

test("Scholar search exposes initial, loading, empty and error states without mock fallback", () => {
  assert.match(browser, /enabled: committedQuery\.length > 0/);
  assert.match(browser, /KnowledgeSearchSkeleton/);
  assert.match(browser, /KnowledgeSearchError/);
  assert.match(browser, /未找到与「\{committedQuery\}」匹配的学者/);
  assert.match(browser, /请尝试完整姓名或英文姓名/);
  assert.doesNotMatch(browser, /data-scholars|MockKnowledgeClient/);
});

test("Scholar result, paper and coauthor links preserve opaque IDs", () => {
  const scholarId = "author:legacy/何恺明?source=kb";
  const returnTo = "/knowledge/scholars?q=Hinton";
  const href = scholarHref(scholarId, returnTo);
  const segment = new URL(href, "https://local.test").pathname
    .slice("/knowledge/scholars/".length);

  assert.equal(scholarIdFromRouteParam(segment), scholarId);
  assert.equal(new URL(href, "https://local.test").searchParams.get("returnTo"), returnTo);
  assert.match(card, /scholarHref\(scholar\.id, returnTo\)/);
  assert.match(detail, /paperHref\(paper\.id, \{ mode: "create", source: currentPath \}\)/);
  assert.match(detail, /scholarHref\(coauthor\.id, safeReturnTo\)/);
  assert.match(route, /scholarIdFromRouteParam\(scholarId\)/);
  assert.match(route, /normalizeInternalReturnTo\(query\.returnTo\)/);
  assert.doesNotMatch(`${card}\n${detail}\n${route}`, /decodeURIComponent/);
});

test("Scholar search restores q, preserves it in returnTo and keeps cached data visible", () => {
  assert.match(browser, /searchParams\.get\("q"\)/);
  assert.match(browser, /router\.replace\(`\/knowledge\/scholars/);
  assert.match(browser, /ScholarCard key=\{scholar\.id\} scholar=\{scholar\} returnTo=\{returnTo\}/);
  assert.match(browser, /isPending && !data/);
  assert.doesNotMatch(browser, /isPending \|\| isFetching/);
  assert.match(detail, /href=\{safeReturnTo\}/);
});

test("Scholar detail hides absent optional sections and keeps a recoverable error state", () => {
  assert.match(detail, /if \(!values\.length\) return null/);
  assert.match(detail, /data\.papers\.length === 0 && data\.coauthors\.length === 0/);
  assert.match(detail, /暂无论文或合作学者信息/);
  assert.match(detail, /无法加载学者详情/);
  assert.match(detail, /返回学者库/);
  assert.match(detail, /refetch\(\)/);
});

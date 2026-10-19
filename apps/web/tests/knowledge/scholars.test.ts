import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createMockScholarProvider } from "../../features/knowledge/scholars/mock-provider";
import {
  DEMO_SCHOLARS,
  DEMO_SCHOLAR_PAPER_IDS,
} from "../../features/knowledge/scholars/mock-data";
import {
  formatScholarMetric,
  recentCitations,
  scholarInitials,
  scholarName,
} from "../../features/knowledge/scholars/presentation";
import { mockPaperDetail } from "../../clients/knowledge/mock-data";
import {
  scholarHref,
  scholarIdFromRouteParam,
} from "../../lib/navigation/scholar";

const provider = createMockScholarProvider(0);
const source = (path: string) => readFileSync(path, "utf8");

test("V2 defaults to all six demo scholars; search matches Chinese or English names only", async () => {
  assert.equal((await provider.search("")).length, 6);
  assert.equal(
    (await provider.search("  林知遥  "))[0].scholar_id,
    DEMO_SCHOLARS[0].scholar_id,
  );
  assert.equal(
    (await provider.search("AVERY mORGAN"))[0].name_en,
    "Avery Morgan",
  );
  assert.equal((await provider.search("Chen")).length, 1);
  assert.deepEqual(await provider.search("不存在的学者"), []);
  assert.deepEqual(await provider.search("星澜大学"), []);
});

test("detail resolves only exact opaque IDs, preserves identities and returns not found", async () => {
  for (const scholar of DEMO_SCHOLARS) {
    assert.deepEqual(
      (await provider.detail(scholar.scholar_id))?.scholar,
      scholar,
    );
  }
  assert.equal(await provider.detail("unknown"), null);
  assert.equal(await provider.detail("林知遥"), null);
});

test("mock responses cannot mutate subsequent profile or publication results", async () => {
  const first = (await provider.search(""))[0];
  first.name_zh = "mutated";
  first.metrics!.citation_count = 999;
  assert.equal((await provider.search(""))[0].name_zh, "林知遥");
  const detail = (await provider.detail(DEMO_SCHOLARS[0].scholar_id))!;
  detail.papers[0].authors.push("mutated");
  assert.ok(
    !(await provider.detail(
      DEMO_SCHOLARS[0].scholar_id,
    ))!.papers[0].authors.includes("mutated"),
  );
});

test("publication relationships reuse existing paper IDs and metadata, without author-name matching", async () => {
  for (const [id, paperIds] of Object.entries(DEMO_SCHOLAR_PAPER_IDS)) {
    const detail = (await provider.detail(id))!;
    assert.deepEqual(
      detail.papers.map((paper) => paper.id),
      [...new Set(paperIds)],
    );
    for (const paper of detail.papers)
      assert.deepEqual(paper, mockPaperDetail(paper.id));
  }
  assert.deepEqual(
    (await provider.detail(DEMO_SCHOLARS[4].scholar_id))?.papers,
    [],
  );
});

test("missing metrics remain missing; genuine zero is displayed as zero", () => {
  assert.equal(formatScholarMetric(null), "暂无数据");
  assert.equal(formatScholarMetric(undefined), "暂无数据");
  assert.equal(formatScholarMetric(Number.NaN), "暂无数据");
  assert.equal(formatScholarMetric(-1), "暂无数据");
  assert.equal(formatScholarMetric(0), "0");
  assert.equal(formatScholarMetric(2460), "2,460");
});

test("citation window is 2022–2026; sparse years stay sparse and input stays unchanged", () => {
  const input = [
    { year: 2026, count: 0 },
    { year: 2021, count: 4 },
    { year: 2024, count: 12 },
    { year: 2023, count: null },
    { year: 2027, count: 5 },
    { year: 2025, count: -1 },
  ];
  assert.deepEqual(recentCitations(input), [
    { year: 2024, count: 12 },
    { year: 2026, count: 0 },
  ]);
  assert.equal(input[0].year, 2026);
  assert.deepEqual(recentCitations(null), []);
  assert.notEqual(
    DEMO_SCHOLARS[0].metrics!.citation_count,
    recentCitations(DEMO_SCHOLARS[0].annual_citations).reduce(
      (total, item) => total + item.count,
      0,
    ),
  );
});

test("names and avatar initials support English-only, Chinese-only and missing values", () => {
  assert.equal(scholarInitials(" Liu Liu "), "LL");
  assert.equal(scholarInitials("Avery Morgan"), "AM");
  assert.equal(scholarInitials(null), "?");
  assert.equal(scholarName(DEMO_SCHOLARS[1]), "Avery Morgan");
  assert.equal(scholarName(DEMO_SCHOLARS[5]), "周予安");
  assert.equal(scholarName({ scholar_id: "unknown" }), "姓名暂缺");
});

test("search and detail support cancellation, including cancellation before loading", async () => {
  const delayed = createMockScholarProvider(100);
  const controller = new AbortController();
  const search = delayed.search("", controller.signal);
  const detail = delayed.detail(DEMO_SCHOLARS[0].scholar_id, controller.signal);
  controller.abort();
  await assert.rejects(search, { name: "AbortError" });
  await assert.rejects(detail, { name: "AbortError" });
  await assert.rejects(provider.search("", controller.signal), {
    name: "AbortError",
  });
});

test("encoded scholar links round-trip reserved characters and literal percent escapes with list context", () => {
  for (const id of [
    "author:legacy/何恺明?source=kb",
    DEMO_SCHOLARS[5].scholar_id,
    "id:%252F#fragment",
  ]) {
    const returnTo = "/knowledge/scholars?q=Avery+Morgan";
    const url = new URL(scholarHref(id, returnTo), "https://local.test");
    const segment = url.pathname.slice("/knowledge/scholars/".length);
    assert.equal(scholarIdFromRouteParam(segment), id);
    assert.equal(url.searchParams.get("returnTo"), returnTo);
  }
  // 当前 Next 版本会保留路由参数编码，使用既有边界工具恰好解码一次。
  assert.match(
    source("app/knowledge/scholars/[scholarId]/page.tsx"),
    /scholarIdFromRouteParam\(scholarId\)/,
  );
  assert.match(
    source("app/scholars/[id]/page.tsx"),
    /scholarHref\(scholarIdFromRouteParam\(id\)\)/,
  );
});

test("V2 is locally isolated, handles loading/error/not-found and does not expose fake paper navigation", () => {
  const browser = source(
    "features/knowledge/scholars/components/scholars-browser.tsx",
  );
  const detail = source("features/knowledge/scholars/ScholarDetailPage.tsx");
  const publications = source(
    "features/knowledge/scholars/components/scholar-publications.tsx",
  );
  assert.match(browser, /provider.search\(committedQuery, signal\)/);
  assert.match(detail, /provider.detail\(scholarId, signal\)/);
  assert.doesNotMatch(
    browser + detail,
    /getKnowledgeClient|data-scholars|MockKnowledgeClient/,
  );
  for (const text of [
    "ScholarLoading",
    "ScholarError",
    "refetch()",
    "DemoBadge",
  ])
    assert.ok(browser.includes(text) && detail.includes(text));
  assert.match(detail, /if \(!data\)/);
  assert.match(detail, /未找到该学者/);
  assert.match(detail, /href=\{safeReturnTo\}/);
  assert.match(browser, /searchParams.get\("q"\)/);
  assert.match(browser, /清空搜索/);
  assert.match(publications, /暂无可展示的论文成果/);
  assert.doesNotMatch(publications, /paperHref|href=|onClick=/);
  assert.match(
    source("features/knowledge/scholars/components/profile-parts.tsx"),
    /onError=/,
  );
  assert.doesNotMatch(
    source("features/knowledge/scholars/mock-provider.ts"),
    /NEXT_PUBLIC_KNOWLEDGE_SOURCE\s*=/,
  );
});

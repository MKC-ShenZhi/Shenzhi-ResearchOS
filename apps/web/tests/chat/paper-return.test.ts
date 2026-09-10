import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { normalizeInternalReturnTo } from "../../lib/navigation/internal-return-to";
import { paperHref } from "../../lib/navigation/paper";
import {
  paperReferenceHref,
} from "../../features/chat/services/reference-navigation";
import {
  navigateBackFromPaper,
  PAPER_DETAIL_FALLBACK_ROUTE,
} from "../../features/papers/[id]/paper-back-navigation";
import type { ChatReference } from "../../types/ai-search";

const paper: ChatReference = {
  referenceId: "1",
  resourceType: "paper",
  resourceId: "opaque/paper?id=1",
  title: "Paper",
  content: "abstract",
  metadata: { authors: [], year: null, venue: null },
};

test("Chat paper links carry the current internal Chat URL as returnTo", () => {
  const returnTo = "/agents/ask?session=opaque%2Fsession%3Fv%3D1";

  assert.equal(normalizeInternalReturnTo(returnTo), returnTo);
  assert.equal(
    paperReferenceHref(paper, returnTo),
    "/papers/opaque%2Fpaper%3Fid%3D1?returnTo=%2Fagents%2Fask%3Fsession%3Dopaque%252Fsession%253Fv%253D1",
  );
});

test("Paper Detail rejects external, protocol-relative, and malformed returnTo values", () => {
  const route = readFileSync("app/papers/[id]/page.tsx", "utf8");
  assert.match(route, /searchParams/);
  assert.match(route, /normalizeInternalReturnTo/);
  assert.equal(normalizeInternalReturnTo("https://evil.example/phish"), null);
  assert.equal(normalizeInternalReturnTo("http://evil.example/phish"), null);
  assert.equal(normalizeInternalReturnTo("//evil.example/phish"), null);
  assert.equal(normalizeInternalReturnTo("javascript:alert(1)"), null);
  assert.equal(normalizeInternalReturnTo("data:text/html,phish"), null);
  assert.equal(normalizeInternalReturnTo("/agents\\ask"), null);
  assert.equal(normalizeInternalReturnTo("/agents/ask?x=hello world"), null);
  assert.equal(normalizeInternalReturnTo("/agents/ask?session=opaque"), "/agents/ask?session=opaque");
});

function paperBackRouterSpy() {
  const calls = { replaced: [] as string[] };
  return {
    calls,
    router: {
      replace: (href: string) => { calls.replaced.push(href); },
    },
  };
}

test("Search -> Paper Detail -> Back replaces with the explicit search URL", () => {
  const { calls, router } = paperBackRouterSpy();

  navigateBackFromPaper(router, "/search?q=agent");

  assert.deepEqual(calls.replaced, ["/search?q=agent"]);
  assert.equal(
    paperHref("123", { mode: "create", source: "/search?q=agent" }),
    "/papers/123?returnTo=%2Fsearch%3Fq%3Dagent",
  );
});

test("Search -> Paper Detail -> Graph -> Paper Detail -> Back preserves one external returnTo", () => {
  const source = "/search?q=agent";
  const detail = paperHref("123", { mode: "create", source });
  const detailReturnTo = new URL(detail, "https://local.test").searchParams.get("returnTo");
  const graph = paperHref("123", { mode: "preserve", returnTo: detailReturnTo, graph: true });
  const graphReturnTo = new URL(graph, "https://local.test").searchParams.get("returnTo");
  const returnedDetail = paperHref("123", { mode: "preserve", returnTo: graphReturnTo });
  const returnedDetailReturnTo = new URL(returnedDetail, "https://local.test").searchParams.get("returnTo");
  const recreatedFromGraph = paperHref("123", { mode: "create", source: graph });
  const { calls, router } = paperBackRouterSpy();

  navigateBackFromPaper(router, returnedDetailReturnTo);

  assert.equal(detailReturnTo, source);
  assert.equal(graphReturnTo, source);
  assert.equal(returnedDetailReturnTo, source);
  assert.equal(recreatedFromGraph, returnedDetail);
  assert.deepEqual(calls.replaced, [source]);
  for (const href of [detail, graph, returnedDetail, recreatedFromGraph]) {
    assert.doesNotMatch(href, /returnTo=%2Fpapers%2F/);
  }
});

test("another internal page -> Paper Detail -> Back replaces with that page", () => {
  const { calls, router } = paperBackRouterSpy();

  navigateBackFromPaper(router, "/knowledge/papers");

  assert.deepEqual(calls.replaced, ["/knowledge/papers"]);
});

test("a direct Paper Detail visit falls back to the homepage", () => {
  const { calls, router } = paperBackRouterSpy();

  navigateBackFromPaper(router, null);

  assert.deepEqual(calls.replaced, [PAPER_DETAIL_FALLBACK_ROUTE]);
  assert.equal(PAPER_DETAIL_FALLBACK_ROUTE, "/");
});

test("an absolute external returnTo falls back to the homepage", () => {
  const { calls, router } = paperBackRouterSpy();

  navigateBackFromPaper(router, "https://evil.example/phish");

  assert.deepEqual(calls.replaced, ["/"]);
});

test("a protocol-relative returnTo falls back to the homepage", () => {
  const { calls, router } = paperBackRouterSpy();

  navigateBackFromPaper(router, "//evil.example/phish");

  assert.deepEqual(calls.replaced, ["/"]);
});

test("Paper Detail uses the generic Back label without a source-specific parent", () => {
  const detail = readFileSync("features/papers/[id]/components/paper-topbar.tsx", "utf8");
  const detailPage = readFileSync("features/papers/[id]/PaperDetailPage.tsx", "utf8");
  const navigation = readFileSync("features/papers/[id]/paper-back-navigation.ts", "utf8");

  assert.match(detail, />\s*返回\s*</);
  assert.match(detail, /navigateBackFromPaper\(router, returnTo\)/);
  assert.match(navigation, /router\.replace/);
  assert.doesNotMatch(`${detail}\n${navigation}`, /history\.length|router\.back|router\.push/);
  assert.doesNotMatch(`${detail}\n${detailPage}`, /返回论文检索|返回论文检索页|返回来源|返回对话/);
});

test("Paper entry points create returnTo while Paper scope links preserve it", () => {
  const hook = readFileSync("hooks/use-current-internal-path.ts", "utf8");
  const discovery = readFileSync("features/search/components/paper-card.tsx", "utf8");
  const dashboard = readFileSync("features/knowledge/components/knowledge-dashboard.tsx", "utf8");
  const search = readFileSync("features/knowledge/search/KnowledgeSearchPage.tsx", "utf8");
  const chat = readFileSync("features/chat/components/reference-grid.tsx", "utf8");
  const privateGraph = readFileSync("components/common/graph/node-abstract-card.tsx", "utf8");
  const paperGraph = readFileSync("features/knowledge/graph/components/graph-workbench.tsx", "utf8");

  assert.match(hook, /usePathname\(\)/);
  assert.match(hook, /useSearchParams\(\)/);
  assert.match(discovery, /paperHref\(paper\.id, \{ mode: "create", source: returnTo \}\)/);
  assert.match(dashboard, /paperHref\(item\.id, \{ mode: "create", source: returnTo \}\)/);
  assert.match(search, /returnTo=\{returnTo\}/);
  assert.match(chat, /paperReferenceHref\(ref, returnTo\)/);
  assert.match(privateGraph, /paperHref\(node\.paperId, \{ mode: "create", source: returnTo \}\)/);
  assert.match(paperGraph, /paperHref\(paperId, \{ mode: "preserve", returnTo \}\)/);
  assert.doesNotMatch(paperGraph, /useCurrentInternalPath|currentPath|paperReturnTo/);
});

test("paper return preserves the URL session as the sole restore target", () => {
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");
  const returnTarget = "/agents/ask?session=S1";

  assert.equal(normalizeInternalReturnTo(returnTarget), returnTarget);
  assert.match(hook, /initialSessionId/);
  assert.match(hook, /void openSession\(urlSessionId\)/);
  assert.equal((hook.match(/void openSession\(urlSessionId\)/g) ?? []).length, 1);
  assert.match(hook, /phaseForRestoredStatus/);
});

test("unified detail, graph and compatibility links preserve opaque IDs and safe origins", async () => {
  const { paperExternalUrl, paperDoiUrl } = await import("../../lib/navigation/paper");
  const id = "paper:opaque/%2F?x=1#片段";
  const returnTo = "/knowledge/search?q=robot&yearFrom=2024";
  const detail = paperHref(id, { mode: "create", source: returnTo });
  const graph = paperHref(id, { mode: "create", source: returnTo, graph: true });
  assert.equal(decodeURIComponent(new URL(detail, "https://local.test").pathname.slice(8)), id);
  assert.equal(new URL(graph, "https://local.test").searchParams.get("returnTo"), returnTo);
  assert.equal(
    paperHref(id, { mode: "create", source: "//evil.test" }),
    `/papers/${encodeURIComponent(id)}`,
  );
  assert.equal(paperExternalUrl("javascript:alert(1)"), null);
  assert.equal(paperExternalUrl(null), null);
  assert.equal(paperExternalUrl("https://example.org/paper.pdf"), "https://example.org/paper.pdf");
  assert.equal(paperDoiUrl("doi:10.1234/example"), "https://doi.org/10.1234/example");
  assert.equal(paperDoiUrl("https://doi.org/10.1234/example"), "https://doi.org/10.1234/example");
});

test("paper journey uses one real detail and graph implementation with compatibility redirects", () => {
  const detailPage = readFileSync("features/papers/[id]/PaperDetailPage.tsx", "utf8");
  const assistant = readFileSync("features/papers/[id]/components/paper-assistant-panel.tsx", "utf8");
  const pdf = readFileSync("features/papers/[id]/components/paper-pdf-viewer.tsx", "utf8");
  const rightPanel = readFileSync("features/papers/[id]/components/right-panel.tsx", "utf8");
  const graphRoute = readFileSync("app/papers/[id]/graph/page.tsx", "utf8");
  const legacyDetail = readFileSync("app/knowledge/search/[paperId]/page.tsx", "utf8");
  const legacyGraph = readFileSync("app/knowledge/search/[paperId]/graph/page.tsx", "utf8");

  assert.match(detailPage, /useKnowledgePaper\(paperId\)/);
  assert.match(detailPage, /<PaperPdfViewer/);
  assert.match(detailPage, /<PaperAbstractView/);
  assert.match(detailPage, /<PaperRightPanel/);
  assert.match(assistant, /embedded:\s*true/);
  assert.match(assistant, /kind:\s*"paper"/);
  assert.match(assistant, /ref_id:\s*paper\.id/);
  assert.match(assistant, /web_search:\s*false/);
  assert.match(pdf, /在新窗口打开 PDF/);
  assert.match(pdf, /当前论文暂无可用 PDF 链接/);
  assert.match(pdf, /\/paper-resource\/pdf\?paperId=/);
  assert.match(rightPanel, /相似论文能力正在接入/);
  assert.match(rightPanel, /暂不支持保存笔记/);
  assert.match(graphRoute, /KnowledgeRelationGraphPage/);
  assert.match(legacyDetail, /redirect\(paperHref/);
  assert.match(legacyGraph, /redirect\(paperHref/);
});

test("Paper Detail loads the PDF only after opening Paper and keeps the viewer mounted", () => {
  const detailPage = readFileSync("features/papers/[id]/PaperDetailPage.tsx", "utf8");
  const pdf = readFileSync("features/papers/[id]/components/paper-pdf-viewer.tsx", "utf8");

  assert.match(detailPage, /type PaperViewMode = "abstract" \| "paper"/);
  assert.match(detailPage, /useState<PaperViewMode>\("abstract"\)/);
  assert.match(detailPage, /useState\(false\)/);
  assert.match(detailPage, /if \(nextMode === "paper"\) setHasOpenedPaper\(true\)/);
  assert.match(detailPage, /\{hasOpenedPaper && \(/);
  assert.match(detailPage, /className=\{viewMode === "paper" \? "h-full" : "hidden"\}/);
  assert.doesNotMatch(detailPage, /paper-resource\/pdf\?paperId=/);
  assert.equal((pdf.match(/paper-resource\/pdf\?paperId=/g) ?? []).length, 1);
  assert.match(pdf, /setState\(!pdfUrl \? "no_pdf" : "loading"\)/);
  assert.match(pdf, /当前论文暂无法在线加载 PDF/);
});

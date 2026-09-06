import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { normalizeInternalReturnTo } from "../../lib/navigation/internal-return-to";
import {
  paperReferenceHref,
} from "../../features/chat/services/reference-navigation";
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
  const route = readFileSync("app/knowledge/search/[paperId]/page.tsx", "utf8");
  const detail = readFileSync("features/papers/[id]/components/paper-topbar.tsx", "utf8");
  const grid = readFileSync("features/chat/components/reference-grid.tsx", "utf8");
  assert.match(route, /searchParams/);
  assert.match(route, /normalizeInternalReturnTo/);
  assert.match(detail, /返回对话/);
  assert.match(detail, /返回论文检索/);
  assert.match(grid, /\}, \[references\.length\]\);/);
  assert.equal(normalizeInternalReturnTo("https://evil.example/phish"), null);
  assert.equal(normalizeInternalReturnTo("//evil.example/phish"), null);
  assert.equal(normalizeInternalReturnTo("javascript:alert(1)"), null);
  assert.equal(normalizeInternalReturnTo("/agents\\ask"), null);
  assert.equal(normalizeInternalReturnTo("/agents/ask?x=hello world"), null);
  assert.equal(normalizeInternalReturnTo("/agents/ask?session=opaque"), "/agents/ask?session=opaque");
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
  const { paperHref, paperExternalUrl, paperDoiUrl } = await import("../../lib/navigation/paper");
  const id = "paper:opaque/%2F?x=1#片段";
  const returnTo = "/knowledge/search?q=robot&yearFrom=2024";
  const detail = paperHref(id, returnTo);
  const graph = paperHref(id, returnTo, true);
  assert.equal(decodeURIComponent(new URL(detail, "https://local.test").pathname.slice(8)), id);
  assert.equal(new URL(graph, "https://local.test").searchParams.get("returnTo"), returnTo);
  assert.equal(paperHref(id, "//evil.test"), `/papers/${encodeURIComponent(id)}`);
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
  assert.match(detailPage, /<PaperRightPanel/);
  assert.match(assistant, /embedded:\s*true/);
  assert.match(assistant, /kind:\s*"paper"/);
  assert.match(assistant, /ref_id:\s*paper\.id/);
  assert.match(assistant, /web_search:\s*false/);
  assert.match(pdf, /在新窗口打开 PDF/);
  assert.match(pdf, /当前论文暂无可用 PDF 链接/);
  assert.match(rightPanel, /相似论文能力正在接入/);
  assert.match(rightPanel, /暂不支持保存笔记/);
  assert.match(graphRoute, /KnowledgeRelationGraphPage/);
  assert.match(legacyDetail, /redirect\(paperHref/);
  assert.match(legacyGraph, /redirect\(paperHref/);
});

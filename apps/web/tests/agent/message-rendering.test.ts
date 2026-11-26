import assert from "node:assert/strict";
import test from "node:test";
import { remarkCitations } from "../../features/agent-chat/components/citation-markers";
import { citationTargets, doiUrl, messageTime, MESSAGE_STATUS, referenceDetails,
  REFERENCE_TYPE, safeReferenceUrl } from "../../features/agent-chat/components/message-presentation";
import { messageFixture } from "./message-fixtures";

type Node = Parameters<ReturnType<typeof remarkCitations>>[0];

test("citation numbering follows reference order and repeats share the same target", () => {
  const message = messageFixture();
  const citations = citationTargets(message.references, "test-message");
  const tree: Node = { type: "root", children: [{ type: "paragraph", children: [
    { type: "text", value: "结果 [[cite:r2]]、[[cite:r1]]，再次 [[cite:r2]]。" },
  ] }] };
  remarkCitations({ citations, isStreaming: false })(tree);
  const links = tree.children![0].children!.filter((node) => node.type === "link");
  assert.deepEqual(links.map((node) => node.children![0].value), ["1", "2", "1"]);
  assert.deepEqual(links.map((node) => node.url), ["#test-message-reference-1", "#test-message-reference-2", "#test-message-reference-1"]);
  assert.equal(JSON.stringify(tree).includes("[[cite:"), false);
});

test("citations work in tables and emphasis without changing code, math or existing links", () => {
  const citations = citationTargets(messageFixture().references, "test");
  const protectedNodes: Node[] = ["code", "inlineCode", "math", "inlineMath"].map((type) => ({ type, value: "[[cite:r2]]" }));
  protectedNodes.push({ type: "link", url: "https://example.test/", children: [{ type: "text", value: "[[cite:r2]]" }] });
  const tree: Node = { type: "root", children: [
    { type: "table", children: [{ type: "tableRow", children: [{ type: "tableCell", children: [{ type: "text", value: "[[cite:r2]]" }] }] }] },
    { type: "strong", children: [{ type: "text", value: "[[cite:r1]]" }] },
    ...structuredClone(protectedNodes),
  ] };
  remarkCitations({ citations, isStreaming: false })(tree);
  assert.equal(tree.children![0].children![0].children![0].children![0].type, "link");
  assert.equal(tree.children![1].children![0].type, "link");
  assert.deepEqual(tree.children!.slice(2), protectedNodes);
});

test("partial or unresolved citations do not expose source IDs", () => {
  for (const suffix of ["[[", "[[c", "[[ci", "[[cit", "[[cite", "[[cite:", "[[cite:internal_id"]) {
    const tree: Node = { type: "paragraph", children: [{ type: "text", value: `正文${suffix}` }] };
    remarkCitations({ citations: [], isStreaming: true })(tree);
    assert.deepEqual(tree.children, [{ type: "text", value: "正文" }]);
  }
  const tree: Node = { type: "paragraph", children: [{ type: "text", value: "[[cite:internal_id]]" }] };
  remarkCitations({ citations: [], isStreaming: false })(tree);
  assert.deepEqual(tree.children, [{ type: "text", value: "[引用不可用]" }]);
  const repaired: Node = { type: "paragraph", children: [
    { type: "text", value: "正文[" },
    { type: "link", url: "streamdown:incomplete-link", children: [{ type: "text", value: "cite:internal_id" }] },
  ] };
  remarkCitations({ citations: [], isStreaming: true })(repaired);
  assert.deepEqual(repaired.children, [{ type: "text", value: "正文" }]);
});

test("reference presentation selects fields and omits unavailable optional metadata", () => {
  assert.equal(referenceDetails({ id: "internal", type: "paper", title: "Paper", authors: ["Vaswani", "A", "B"], year: 2017, venue: "NeurIPS" }), "Vaswani et al. · NeurIPS 2017");
  assert.equal(referenceDetails({ id: "internal", type: "webpage", title: "Page", url: "https://www.huggingface.co/docs" }), "huggingface.co");
  assert.equal(referenceDetails({ id: "internal", type: "paper", title: "Paper" }), "");
  assert.equal(REFERENCE_TYPE.paper, "论文");
  assert.equal(REFERENCE_TYPE.webpage, "网页");
});

test("only safe external URLs become navigation targets; DOI links stay on doi.org", () => {
  for (const url of ["javascript:alert(1)", "data:text/html,x", "file:///secret", "//example.test", "https://user:secret@example.test/"]) {
    assert.equal(safeReferenceUrl(url), null);
  }
  assert.equal(safeReferenceUrl("https://example.test/paper"), "https://example.test/paper");
  assert.equal(doiUrl("https://doi.org/10.1/test"), "https://doi.org/10.1%2Ftest");
  assert.equal(doiUrl(null), null);
});

test("Message metadata interprets created_at as seconds and maps all statuses", () => {
  assert.deepEqual(messageTime(1795651200.125), {
    dateTime: "2026-11-26T00:00:00.125Z", label: "2026/11/26 08:00",
  });
  assert.equal(messageTime(Infinity), null);
  assert.deepEqual(Object.keys(MESSAGE_STATUS), ["running", "done", "failed", "stopped", "timeout", "awaiting_input"]);
});

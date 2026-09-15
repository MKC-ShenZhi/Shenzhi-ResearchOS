import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  citedReferenceIds,
  paperReferenceHref,
} from "../../features/chat/services/reference-navigation";
import type { ChatReference } from "../../types/ai-search";

function reference(referenceId: string, resourceId = `opaque-${referenceId}`): ChatReference {
  return {
    referenceId,
    resourceType: "paper",
    resourceId,
    title: `Paper ${referenceId}`,
    content: "abstract",
    metadata: { authors: [], year: null, venue: null },
  };
}

test("citations focus sources and source cards link opaque paper IDs", () => {
  const citations = readFileSync("features/chat/components/citations.tsx", "utf8");
  const grid = readFileSync("features/chat/components/reference-grid.tsx", "utf8");
  const thread = readFileSync("features/chat/components/chat-thread.tsx", "utf8");

  assert.match(citations, /data-text-citation/);
  assert.match(citations, /jump\(id, "source"\)/);
  assert.match(grid, /data-source-citation/);
  assert.match(grid, /paperReferenceHref/);
  assert.match(grid, /resourceId/);
  assert.doesNotMatch(grid, /resourceId \?\? ref\.source_id \?\? referenceId/);
  assert.match(thread, /answer=\{turn\.content\}/);
});

test("reference UI separates cited sources from retrieved evidence", () => {
  const grid = readFileSync("features/chat/components/reference-grid.tsx", "utf8");

  assert.match(grid, /citedReferenceIds/);
  assert.match(grid, /引用来源/);
  assert.match(grid, /查看全部检索资料/);
  assert.match(grid, /references\.length/);
});

test("only valid citations become cited sources, with duplicates removed", () => {
  const references = Array.from({ length: 10 }, (_, index) => reference(String(index + 1)));

  const cited = citedReferenceIds("事实 [1]、[1]，未知 [99]。", references);
  assert.deepEqual(cited, ["1"]);
  assert.equal(cited.length, 1);
  assert.equal(references.length, 10);
  assert.equal(paperReferenceHref(references[0]), "/papers/opaque-1");
  assert.equal(
    paperReferenceHref({ ...references[0], resourceType: "web" }),
    null,
  );
  assert.equal(
    paperReferenceHref({ ...references[0], resourceId: "", source_id: undefined }),
    null,
  );
});

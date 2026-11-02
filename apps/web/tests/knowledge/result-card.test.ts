import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const RESULT_CARD_SOURCE = readFileSync(
  "features/knowledge/search/components/result-card.tsx",
  "utf8",
);
const CARD_LAYOUT_SOURCE = readFileSync("features/knowledge/papers/components/paper-card-layout.tsx", "utf8");
const KNOWLEDGE_TYPES_SOURCE = readFileSync("clients/knowledge/types.ts", "utf8");

test("Knowledge result card does not convert score into a percentage", () => {
  assert.doesNotMatch(RESULT_CARD_SOURCE, /score\s*\*\s*100/);
  assert.doesNotMatch(RESULT_CARD_SOURCE, /Math\.round\([^)]*score[^)]*\)/);
});

test("Knowledge result card uses the shared fallback thumbnail instead of visible rank", () => {
  assert.match(RESULT_CARD_SOURCE, /import \{ getPaperThumbnailUrl \}/);
  assert.match(RESULT_CARD_SOURCE, /thumbnailUrl: getPaperThumbnailUrl\(hit\.imageId\)/);
  assert.match(CARD_LAYOUT_SOURCE, /import \{ PaperThumbnail \}/);
  assert.match(CARD_LAYOUT_SOURCE, /<PaperThumbnail src=\{paper\.thumbnailUrl\}/);
  assert.doesNotMatch(RESULT_CARD_SOURCE, /hit\.rank/);
});

test("Knowledge result card shares the home card layout and display rules", () => {
  assert.match(RESULT_CARD_SOURCE, /<PaperCardLayout/);
  for (const helper of ["formatPaperAuthors", "formatPaperYear", "paperVenueTone", "pickPaperTopics"]) {
    assert.match(RESULT_CARD_SOURCE, new RegExp(`${helper}\\(`), helper);
  }
  assert.match(RESULT_CARD_SOURCE, /<CollectionPicker paperId=\{hit\.id\} \/>/);
  assert.match(RESULT_CARD_SOURCE, /aria-label="关系图谱"/);
});

test("Knowledge search keeps rank in its data contract", () => {
  assert.match(KNOWLEDGE_TYPES_SOURCE, /rank:\s*number \| null/);
});

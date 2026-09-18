import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const RESULT_CARD_SOURCE = readFileSync(
  "features/knowledge/search/components/result-card.tsx",
  "utf8",
);
const KNOWLEDGE_TYPES_SOURCE = readFileSync("clients/knowledge/types.ts", "utf8");

test("Knowledge result card does not convert score into a percentage", () => {
  assert.doesNotMatch(RESULT_CARD_SOURCE, /score\s*\*\s*100/);
  assert.doesNotMatch(RESULT_CARD_SOURCE, /Math\.round\([^)]*score[^)]*\)/);
});

test("Knowledge result card uses the shared fallback thumbnail instead of visible rank", () => {
  assert.match(RESULT_CARD_SOURCE, /import \{ PaperThumbnail \}/);
  assert.match(RESULT_CARD_SOURCE, /<PaperThumbnail/);
  assert.match(RESULT_CARD_SOURCE, /src=\{null\}/);
  assert.doesNotMatch(RESULT_CARD_SOURCE, /hit\.rank/);
});

test("Knowledge search keeps rank in its data contract", () => {
  assert.match(KNOWLEDGE_TYPES_SOURCE, /rank:\s*number \| null/);
});

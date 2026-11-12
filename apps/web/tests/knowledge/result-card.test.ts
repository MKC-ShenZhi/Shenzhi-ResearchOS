import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { pickPaperTopics, toPaperCardModel } from "../../features/knowledge/papers/paper-card-model.js";
import { topicHref, topicIdFromRouteParam } from "../../features/knowledge/topics/topic-url-state.js";

const RESULT_CARD_SOURCE = readFileSync(
  "features/knowledge/search/components/result-card.tsx",
  "utf8",
);
const CARD_LAYOUT_SOURCE = readFileSync("features/knowledge/papers/components/paper-card-layout.tsx", "utf8");
const CARD_MODEL_SOURCE = readFileSync("features/knowledge/papers/paper-card-model.ts", "utf8");
const KNOWLEDGE_TYPES_SOURCE = readFileSync("clients/knowledge/types.ts", "utf8");

test("Knowledge result card does not convert score into a percentage", () => {
  assert.doesNotMatch(RESULT_CARD_SOURCE, /score\s*\*\s*100/);
  assert.doesNotMatch(RESULT_CARD_SOURCE, /Math\.round\([^)]*score[^)]*\)/);
});

test("Knowledge result card uses the shared fallback thumbnail instead of visible rank", () => {
  assert.match(CARD_MODEL_SOURCE, /thumbnailUrl: getPaperThumbnailUrl\(paper\.imageId\)/);
  assert.match(CARD_LAYOUT_SOURCE, /import \{ PaperThumbnail \}/);
  assert.match(CARD_LAYOUT_SOURCE, /<PaperThumbnail src=\{paper\.thumbnailUrl\}/);
  assert.doesNotMatch(RESULT_CARD_SOURCE, /hit\.rank/);
});

test("Knowledge result card shares the home card layout and display rules", () => {
  assert.match(RESULT_CARD_SOURCE, /<PaperCardLayout/);
  assert.match(RESULT_CARD_SOURCE, /paper=\{toPaperCardModel\(hit\)\}/);
  assert.match(RESULT_CARD_SOURCE, /<CollectionPicker paperId=\{hit\.id\} \/>/);
  assert.match(RESULT_CARD_SOURCE, /aria-label="关系图谱"/);
});

test("Knowledge search keeps rank in its data contract", () => {
  assert.match(KNOWLEDGE_TYPES_SOURCE, /rank:\s*number \| null/);
});

test("paper cards use distinct named topics and link by their full encoded ID", () => {
  const topic = { id: "openalex:topic:T10028", nameZh: "语言模型", nameEn: "Language models" };
  const english = { id: "openalex:topic:T10181", nameZh: null, nameEn: "Computer vision" };
  assert.deepEqual(pickPaperTopics([
    { ...topic, nameZh: " ", nameEn: " " }, { ...topic, id: "" },
    topic, { ...topic, nameZh: "重复" }, english,
  ]), [topic, english]);
  assert.deepEqual(pickPaperTopics(undefined), []);
  assert.deepEqual(pickPaperTopics([]), []);

  const href = topicHref(topic.id);
  assert.equal(href, "/knowledge/topics/openalex%3Atopic%3AT10028");
  assert.equal(topicIdFromRouteParam(href.split("/").at(-1)!), topic.id);
  const paper = toPaperCardModel({
    id: "paper:example", title: "Example", year: 2026, venue: "ICLR",
    authors: ["First Author", "Second Author"], abstract: null, topics: [topic, topic, english],
  });
  assert.deepEqual(paper.topics, [topic, english]);
  assert.equal(paper.date, "2026");
  assert.equal(paper.authors, "First Author · Second Author");
  assert.equal(paper.thumbnailUrl, null);
  assert.doesNotMatch(RESULT_CARD_SOURCE, /hit\.(keywords|subjects)/);
  assert.match(CARD_LAYOUT_SOURCE, /paper\.topics\.length > 0/);
  assert.match(CARD_LAYOUT_SOURCE, /topic\.nameZh \|\| topic\.nameEn/);
  assert.match(CARD_LAYOUT_SOURCE, /<Link\s+key=\{topic\.id\}\s+href=\{topicHref\(topic\.id\)\}\s+prefetch=\{false\}[^>]*>\s*#\{name\}/);
});

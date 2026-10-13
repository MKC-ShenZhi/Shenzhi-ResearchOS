import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { filterTopics, groupTopics, readTopicViewState, updateTopicViewParams } from "../../features/knowledge/topics/topic-url-state";
import { selectFeaturedTopics } from "../../features/knowledge/topics/topic-metadata";
import { MOCK_TOPICS } from "../../clients/knowledge/mock-data";

test("主题筛选状态从 URL 读取并按名称和分类过滤", () => { const state = readTopicViewState(new URLSearchParams("q=大语言&category=大语言模型")); const topics = filterTopics(MOCK_TOPICS, state); assert.equal(state.query, "大语言"); assert.ok(topics.some((topic) => topic.id === "large-language-models")); assert.ok(topics.every((topic) => topic.category === "大语言模型")); });
test("最新主题目录包含 293 条主题和 8 个分类", () => { const groups = groupTopics(MOCK_TOPICS); assert.equal(MOCK_TOPICS.length, 293); assert.equal(groups.length, 8); assert.equal(new Set(MOCK_TOPICS.map((topic) => topic.id)).size, 293); });
test("主题搜索支持 ID 和 subjectQuery", () => { assert.deepEqual(filterTopics(MOCK_TOPICS, readTopicViewState(new URLSearchParams("q=contrastive-learning"))).map((topic) => topic.id), ["contrastive-learning"]); assert.ok(filterTopics(MOCK_TOPICS, readTopicViewState(new URLSearchParams("q=machine translation"))).some((topic) => topic.id === "machine-translation")); });
test("主题搜索支持结构化创作者信息", () => {
  const topics = [{ ...MOCK_TOPICS.find((topic) => topic.id === "deep-learning")!, author: { id: "shenzhi", name: "ShenZhi" } }];
  const results = filterTopics(topics, readTopicViewState(new URLSearchParams("q=shen")));
  assert.deepEqual(results.map((topic) => topic.id), ["deep-learning"]);
});

test("主题搜索支持中文、英文、缩写与 subjectQuery，并组合分类", () => {
  for (const query of ["大语言模型", "large language models", "llm", "machine translation", "ＭＡＣＨＩＮＥ ＴＲＡＮＳＬＡＴＩＯＮ"]) {
    const matches = filterTopics(MOCK_TOPICS, { query, category: "" });
    assert.ok(matches.length > 0, query);
  }
  const result = filterTopics(MOCK_TOPICS, { query: "translation", category: "自然语言处理" });
  assert.ok(result.some((topic) => topic.id === "machine-translation"));
  assert.ok(result.every((topic) => topic.category === "自然语言处理"));
  assert.deepEqual(filterTopics(MOCK_TOPICS, { query: "no-such-topic-xyz", category: "" }), []);
  assert.deepEqual(filterTopics(MOCK_TOPICS, { query: "machine translation", category: "计算机视觉" }), []);
});

test("URL 更新保留分类和其他参数，清空与浏览器历史可恢复状态", () => {
  const original = new URLSearchParams("category=自然语言处理&theme=dark");
  const searched = updateTopicViewParams(original, { query: " machine translation " });
  assert.equal(searched.get("q"), "machine translation");
  assert.equal(searched.get("category"), "自然语言处理");
  assert.equal(searched.get("theme"), "dark");
  assert.equal(original.has("q"), false);
  const categoryChanged = updateTopicViewParams(searched, { category: "大语言模型" });
  assert.equal(categoryChanged.get("q"), "machine translation");
  const cleared = updateTopicViewParams(categoryChanged, { query: "" });
  assert.equal(cleared.has("q"), false);
  assert.equal(cleared.get("category"), "大语言模型");
  assert.deepEqual(readTopicViewState(new URLSearchParams(searched.toString())), { query: "machine translation", category: "自然语言处理" });
});

test("精选 ID 配置不受目录顺序影响，并跳过缺失或禁用的主题", () => {
  const featured = selectFeaturedTopics(MOCK_TOPICS);
  assert.deepEqual(featured.map((t) => t.id), ["reinforcement-learning", "deep-learning"]);
  assert.deepEqual(selectFeaturedTopics([...MOCK_TOPICS].reverse()), featured);
  assert.deepEqual(selectFeaturedTopics(featured.map((t) => ({ ...t, enabled: false }))), []);
  assert.deepEqual(selectFeaturedTopics([]), []);
});

test("演示目录与后端 JSON 保持相同字段和数据", () => {
  const catalog = JSON.parse(readFileSync("../backend/app/data/topic_catalog.json", "utf8"));
  assert.deepEqual(MOCK_TOPICS, catalog);
});

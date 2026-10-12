import assert from "node:assert/strict";
import test from "node:test";
import { filterTopics, groupTopics, readTopicViewState } from "../../features/knowledge/topics/topic-url-state";
import { MOCK_TOPICS } from "../../clients/knowledge/mock-data";

test("主题筛选状态从 URL 读取并按名称和分类过滤", () => { const state = readTopicViewState(new URLSearchParams("q=大语言&category=大语言模型")); const topics = filterTopics(MOCK_TOPICS, state); assert.equal(state.query, "大语言"); assert.ok(topics.some((topic) => topic.id === "large-language-models")); assert.ok(topics.every((topic) => topic.category === "大语言模型")); });
test("最新主题目录包含 293 条主题和 8 个分类", () => { const groups = groupTopics(MOCK_TOPICS); assert.equal(MOCK_TOPICS.length, 293); assert.equal(groups.length, 8); assert.equal(new Set(MOCK_TOPICS.map((topic) => topic.id)).size, 293); });
test("主题搜索支持 ID 和 subjectQuery", () => { assert.deepEqual(filterTopics(MOCK_TOPICS, readTopicViewState(new URLSearchParams("q=contrastive-learning"))).map((topic) => topic.id), ["contrastive-learning"]); assert.ok(filterTopics(MOCK_TOPICS, readTopicViewState(new URLSearchParams("q=machine translation"))).some((topic) => topic.id === "machine-translation")); });
test("主题搜索支持结构化创作者信息", () => {
  const topics = [{ ...MOCK_TOPICS.find((topic) => topic.id === "deep-learning")!, author: { id: "shenzhi", name: "ShenZhi" } }];
  const results = filterTopics(topics, readTopicViewState(new URLSearchParams("q=shen")));
  assert.deepEqual(results.map((topic) => topic.id), ["deep-learning"]);
});

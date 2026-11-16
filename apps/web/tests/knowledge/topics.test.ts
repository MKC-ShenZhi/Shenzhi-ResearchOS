import assert from "node:assert/strict";
import test from "node:test";
import { filterTopics, groupTopics, readTopicViewState, topicHref, topicIdFromRouteParam, topicSquareHref, updateTopicViewParams } from "../../features/knowledge/topics/topic-url-state";
import { selectFeaturedTopics } from "../../features/knowledge/topics/topic-metadata";
import { MockKnowledgeClient } from "../../clients/knowledge/mock";
import { MOCK_TOPICS } from "../../clients/knowledge/mock-data";

const [nlpTopic, robustnessTopic] = MOCK_TOPICS;
const aiCategory = nlpTopic.category;
const visionCategory = "openalex:subfield:1707";

test("主题按 Subfield ID 筛选，并用名称和简介搜索", () => {
  const topics = [nlpTopic, { ...robustnessTopic, category: visionCategory }];
  const state = readTopicViewState(new URLSearchParams({ q: "自然语言", category: aiCategory }));
  assert.deepEqual(filterTopics(topics, state), [nlpTopic]);
  assert.deepEqual(filterTopics(topics, { query: "", category: visionCategory }), [topics[1]]);
  assert.deepEqual(filterTopics(topics, { query: "自然语言", category: visionCategory }), []);
  for (const query of [nlpTopic.id, "natural language", "ＮＡＴＵＲＡＬ ＬＡＮＧＵＡＧＥ", "表示方法"]) {
    assert.deepEqual(filterTopics(topics, { query, category: "" }), [nlpTopic]);
  }
  assert.deepEqual(filterTopics(topics, { query: "no-such-topic", category: "" }), []);
});

test("全部与 Subfield 的数量均来自当前主题项", async () => {
  const catalog = await new MockKnowledgeClient().topics();
  assert.equal(catalog.total, catalog.items.length);
  assert.equal(catalog.total, new Set(catalog.items.map((topic) => topic.id)).size);
  const groups = new Map(groupTopics(catalog.items));
  assert.equal(catalog.categories.reduce((sum, category) => sum + category.total, 0), catalog.total);
  for (const category of catalog.categories) {
    assert.equal(groups.get(category.id)?.length, category.total);
    assert.equal(groups.get(category.id)?.[0].categoryName, category.name);
  }
});

test("URL 更新保留分类和其他参数，清空与浏览器历史可恢复状态", () => {
  const original = new URLSearchParams({ category: aiCategory, theme: "dark" });
  const searched = updateTopicViewParams(original, { query: " natural language " });
  assert.equal(searched.get("q"), "natural language");
  assert.equal(searched.get("category"), aiCategory);
  assert.equal(searched.get("theme"), "dark");
  assert.equal(original.has("q"), false);
  const categoryChanged = updateTopicViewParams(searched, { category: visionCategory });
  assert.equal(categoryChanged.get("q"), "natural language");
  const cleared = updateTopicViewParams(categoryChanged, { query: "" });
  assert.equal(cleared.has("q"), false);
  assert.equal(cleared.get("category"), visionCategory);
  assert.deepEqual(readTopicViewState(new URLSearchParams(searched.toString())), { query: "natural language", category: aiCategory });
});

test("详情链接保存完整广场 URL，刷新后返回恢复搜索、分类和结果", () => {
  for (const params of [
    new URLSearchParams({ q: "自然语言" }),
    new URLSearchParams({ category: aiCategory }),
    new URLSearchParams({ q: "自然语言", category: aiCategory, view: "grid" }),
    new URLSearchParams({ q: "natural language", category: aiCategory }),
  ]) {
    const source = `/knowledge/topics?${params.toString()}`;
    const state = readTopicViewState(params);
    const results = filterTopics(MOCK_TOPICS, state);
    assert.ok(results.length > 0);
    const href = topicHref(results[0].id, source);
    // Reconstruct from the URL alone, as on a reload or opening in a new tab.
    const detailUrl = new URL(href, "https://shenzhi.test");
    assert.equal(detailUrl.pathname, `/knowledge/topics/${encodeURIComponent(results[0].id)}`);
    const restored = topicSquareHref(detailUrl.searchParams.get("returnTo"));
    assert.equal(restored, source);
    const restoredState = readTopicViewState(new URL(restored, detailUrl).searchParams);
    assert.deepEqual(restoredState, state);
    assert.deepEqual(filterTopics(MOCK_TOPICS, restoredState), results);
  }
});

test("直接访问详情和默认广场来源安全返回主题广场，Topic ID 仍按路径段编码", () => {
  assert.equal(topicHref("deep-learning"), "/knowledge/topics/deep-learning");
  assert.equal(topicSquareHref(undefined), "/knowledge/topics");
  assert.equal(topicSquareHref(null), "/knowledge/topics");
  const href = topicHref("opaque/id ?中文", "/knowledge/topics");
  const url = new URL(href, "https://shenzhi.test");
  assert.equal(url.pathname, `/knowledge/topics/${encodeURIComponent("opaque/id ?中文")}`);
  assert.equal(topicSquareHref(url.searchParams.get("returnTo")), "/knowledge/topics");
});

test("非法或非主题广场的 returnTo 不进入链接且返回默认广场", () => {
  for (const value of [
    "", "https://evil.test/knowledge/topics", "//evil.test/knowledge/topics",
    "javascript:alert(1)", "/\\evil.test/knowledge/topics", "/knowledge/topics\\evil",
    " /knowledge/topics", "/knowledge/topics\n", "/knowledge/topics\u0000",
    "/knowledge/topics/../topics", "/knowledge/%74opics", "/knowledge/topics/%2e%2e",
    "/knowledge/topics/deep-learning", "/knowledge/topics-extra", "/knowledge/papers",
    "?q=llm", "%2Fknowledge%2Ftopics", ["/knowledge/topics"],
  ]) {
    assert.equal(topicSquareHref(value), "/knowledge/topics", String(value));
    if (typeof value === "string") {
      assert.equal(topicHref("deep-learning", value), "/knowledge/topics/deep-learning", value);
    }
  }
});

test("精选 ID 配置不受目录顺序影响，并跳过缺失或禁用的主题", () => {
  const featured = selectFeaturedTopics(MOCK_TOPICS);
  assert.deepEqual(featured.map((t) => t.id), [nlpTopic.id, robustnessTopic.id]);
  assert.deepEqual(selectFeaturedTopics([...MOCK_TOPICS].reverse()), featured);
  assert.deepEqual(selectFeaturedTopics(featured.map((t) => ({ ...t, enabled: false }))), []);
  assert.deepEqual(selectFeaturedTopics([]), []);
});

test("主题详情统一还原 Next 路由传入的编码 ID，保留原始和非法 ID", () => {
  assert.equal(topicIdFromRouteParam(encodeURIComponent(nlpTopic.id)), nlpTopic.id);
  assert.equal(topicIdFromRouteParam(nlpTopic.id), nlpTopic.id);
  assert.equal(topicIdFromRouteParam("invalid%"), "invalid%");
});

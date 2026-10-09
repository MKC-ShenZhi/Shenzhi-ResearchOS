import assert from "node:assert/strict";
import test from "node:test";
import { filterTopics, groupTopics, readTopicViewState } from "../../features/knowledge/topics/topic-url-state";
import { MOCK_TOPICS } from "../../clients/knowledge/mock-data";

test("主题筛选状态从 URL 读取并按名称和分类过滤", () => { const state = readTopicViewState(new URLSearchParams("q=大语言&category=自然语言处理")); const topics = filterTopics(MOCK_TOPICS, state); assert.equal(state.query, "大语言"); assert.deepEqual(topics.map((topic) => topic.id), ["large-language-models"]); });
test("主题按一级分类分组", () => { const groups = groupTopics(MOCK_TOPICS); assert.deepEqual(groups.map(([category]) => category), ["机器学习", "自然语言处理"]); assert.equal(groups[0][1].length, 4); assert.equal(groups[1][1].length, 3); });

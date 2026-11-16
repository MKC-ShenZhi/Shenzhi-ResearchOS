import assert from "node:assert/strict";
import test from "node:test";
import { InfiniteQueryObserver, QueryClient } from "@tanstack/react-query";
import { KnowledgeClientError } from "../../clients/knowledge/client";
import type { KnowledgeClient, KnowledgePaperBrowseResponse } from "../../clients/knowledge";
import {
  canAutoLoadTopicPapers,
  nextTopicPaperOffset,
  topicPaperQueryOptions,
} from "../../features/knowledge/topics/detail/topic-paper-query";

function page(offset: number, count: number, total: number): KnowledgePaperBrowseResponse {
  return {
    total,
    offset,
    limit: 10,
    results: Array.from({ length: count }, (_, index) => ({
      id: `paper-${offset + index}`, imageId: null, title: `Paper ${offset + index}`, abstract: null,
      authors: [], year: null, venue: null, keywords: [], subjects: [], score: null,
      rank: offset + index + 1, provenance: { source: "fixture" },
    })),
  };
}

function harness(search: KnowledgeClient["topicPapers"]) {
  const client = new QueryClient();
  const observer = new InfiniteQueryObserver(client, {
    ...topicPaperQueryOptions("openalex:topic:T10028", search),
    enabled: false, retryDelay: 0, gcTime: Infinity,
  });
  const unsubscribe = observer.subscribe(() => {});
  return { observer, close: () => { unsubscribe(); client.clear(); } };
}

test("分页按实际返回条数递进，到总数或空页停止", () => {
  assert.equal(nextTopicPaperOffset(page(0, 7, 30)), 7);
  assert.equal(nextTopicPaperOffset(page(7, 10, 30)), 17);
  assert.equal(nextTopicPaperOffset(page(20, 10, 30)), undefined);
  assert.equal(nextTopicPaperOffset(page(10, 0, 30)), undefined);
  assert.equal(nextTopicPaperOffset(page(1000, 10, 1500)), 1010);
});

test("TanStack 分页传完整 Topic ID，超过 1000 继续直到末页", async (t) => {
  const offsets: number[] = [];
  const total = 1023;
  const { observer, close } = harness(async (id, offset, limit) => {
    assert.equal(id, "openalex:topic:T10028");
    offsets.push(offset);
    return page(offset, Math.min(limit, total - offset), total);
  });
  t.after(close);
  await observer.refetch();
  while (observer.getCurrentResult().hasNextPage) await observer.fetchNextPage();
  await observer.fetchNextPage();
  assert.deepEqual(offsets, Array.from({ length: 103 }, (_, i) => i * 10));
  assert.equal(observer.getCurrentResult().data?.pages.at(-1)?.results.length, 3);
});

test("下一页失败保留数据并暂停自动加载，手动只重试失败的 offset", async (t) => {
  const offsets: number[] = [];
  let fail = true;
  const { observer, close } = harness(async (_topicId, offset = 0) => {
    offsets.push(offset);
    if (offset === 10 && fail) throw new KnowledgeClientError("UNKNOWN", "失败", { retryable: false });
    return page(offset, 10, 20);
  });
  t.after(close);
  await observer.refetch();
  await observer.fetchNextPage();
  const failed = observer.getCurrentResult();
  assert.equal(failed.isFetchNextPageError, true);
  assert.equal(failed.isLoadingError, false);
  assert.deepEqual(failed.data?.pageParams, [0]);
  assert.equal(failed.data?.pages[0].results.length, 10);
  assert.equal(canAutoLoadTopicPapers(failed), false);
  fail = false;
  await observer.fetchNextPage({ cancelRefetch: false });
  const recovered = observer.getCurrentResult();
  assert.deepEqual(offsets, [0, 10, 10]);
  assert.deepEqual(recovered.data?.pageParams, [0, 10]);
  assert.equal(new Set(recovered.data?.pages.flatMap((p) => p.results.map((hit) => hit.id))).size, 20);
  assert.equal(recovered.isFetchNextPageError, false);
  assert.equal(recovered.hasNextPage, false);
});

test("首次失败没有缓存，重新加载后恢复；可重试错误最多重试一次", async (t) => {
  let requests = 0;
  let fail = true;
  const { observer, close } = harness(async () => {
    requests++;
    if (fail) throw KnowledgeClientError.timeout();
    return page(0, 1, 1);
  });
  t.after(close);
  await observer.refetch();
  assert.equal(requests, 2);
  assert.equal(observer.getCurrentResult().isLoadingError, true);
  assert.equal(observer.getCurrentResult().data, undefined);
  fail = false;
  await observer.refetch();
  assert.equal(requests, 3);
  assert.equal(observer.getCurrentResult().hasNextPage, false);
});

test("重复下一页触发合并为一次请求，加载中不自动请求", async (t) => {
  const offsets: number[] = [];
  let resolveNext!: (value: KnowledgePaperBrowseResponse) => void;
  const { observer, close } = harness(async (_topicId, offset = 0) => {
    offsets.push(offset);
    if (offset === 10) return new Promise((resolve) => { resolveNext = resolve; });
    return page(0, 10, 20);
  });
  t.after(close);
  await observer.refetch();
  const first = observer.fetchNextPage({ cancelRefetch: false });
  const second = observer.fetchNextPage({ cancelRefetch: false });
  assert.equal(canAutoLoadTopicPapers(observer.getCurrentResult()), false);
  resolveNext(page(10, 10, 20));
  await Promise.all([first, second]);
  assert.deepEqual(offsets, [0, 10]);
  assert.deepEqual(observer.getCurrentResult().data?.pageParams, [0, 10]);
});

test("正常结果可自动加载；空的后续页停止，保留已有数据", async (t) => {
  const { observer, close } = harness(async (_topicId, offset = 0) => page(offset, offset ? 0 : 10, 30));
  t.after(close);
  await observer.refetch();
  assert.equal(canAutoLoadTopicPapers(observer.getCurrentResult()), true);
  await observer.fetchNextPage();
  assert.equal(observer.getCurrentResult().hasNextPage, false);
  assert.equal(observer.getCurrentResult().data?.pages[0].results.length, 10);
});

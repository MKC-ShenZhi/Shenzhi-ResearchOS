import assert from "node:assert/strict";
import test from "node:test";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { clearOtherInteractionIdentities, refreshCollectionQueries, refreshPaperQueries, refreshTopicQueries } from "../../features/knowledge/interactions/cache";
import { likePaper, fetchMyLikes, fetchMyCollectedPapers, fetchMyTopicFollows } from "../../clients/backend/interactions";

function client() { return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } }); }

test("card, detail and saved likes observe the same server change", async () => {
  const cache = client();
  const key = ["paper-interaction", "a", "paper"];
  let server = { liked: false, likeCount: 0 };
  const options = { queryKey: key, queryFn: async () => server, staleTime: Infinity };
  await cache.fetchQuery(options);
  const card = new QueryObserver(cache, options);
  const detail = new QueryObserver(cache, options);
  const seen: boolean[] = [];
  const stopCard = card.subscribe((result) => { if (result.data) seen.push(result.data.liked); });
  const stopDetail = detail.subscribe(() => {});
  cache.setQueryData(["my-likes", "a", 1], { total: 0 });
  server = { liked: true, likeCount: 2 };
  await refreshPaperQueries(cache, "a", "paper");
  assert.deepEqual(card.getCurrentResult().data, server);
  assert.deepEqual(detail.getCurrentResult().data, server);
  assert.ok(seen.includes(true));
  assert.equal(cache.getQueryState(["my-likes", "a", 1])?.isInvalidated, true);
  stopCard(); stopDetail(); cache.clear();
});

test("an in-flight pre-write read cannot overwrite a refreshed interaction", async () => {
  const cache = client();
  const key = ["paper-interaction", "a", "paper"];
  let finishOld!: (value: { liked: boolean }) => void;
  let calls = 0;
  const observer = new QueryObserver(cache, {
    queryKey: key,
    queryFn: () => ++calls === 1
      ? new Promise<{ liked: boolean }>((resolve) => { finishOld = resolve; })
      : Promise.resolve({ liked: true }),
  });
  const stop = observer.subscribe(() => {});
  await refreshPaperQueries(cache, "a", "paper");
  finishOld({ liked: false });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(cache.getQueryData(key), { liked: true });
  stop(); cache.clear();
});

test("account switches and sign-out clear all personal interaction lists", () => {
  const cache = client();
  const kinds = ["paper-interaction", "topic-interaction", "my-likes", "my-collected-papers", "my-topic-follows", "collection-folder-papers"];
  for (const kind of kinds) for (const user of ["", "a", "b"]) cache.setQueryData([kind, user, "id"], { owner: user });
  clearOtherInteractionIdentities(cache, "b");
  for (const kind of kinds) {
    assert.equal(cache.getQueryData([kind, "a", "id"]), undefined);
    assert.deepEqual(cache.getQueryData([kind, "b", "id"]), { owner: "b" });
  }
  clearOtherInteractionIdentities(cache, "");
  for (const kind of kinds) assert.equal(cache.getQueryData([kind, "b", "id"]), undefined);
  assert.deepEqual(cache.getQueryData(["paper-interaction", "", "id"]), { owner: "" });
  cache.clear();
});

test("collection and follow changes invalidate every affected view and keep other private lists separate", async () => {
  const cache = client();
  for (const kind of ["paper-interaction", "my-collected-papers", "collection-folder-papers", "topic-interaction", "my-topic-follows"]) {
    for (const user of ["", "a", "b"]) cache.setQueryData([kind, user, "id"], { marker: user });
  }
  await refreshCollectionQueries(cache, "a", "id");
  await refreshTopicQueries(cache, "a", "id");
  for (const kind of ["my-collected-papers", "collection-folder-papers", "my-topic-follows"]) {
    assert.equal(cache.getQueryState([kind, "a", "id"])?.isInvalidated, true);
    assert.equal(cache.getQueryState([kind, "b", "id"])?.isInvalidated, false);
  }
  assert.equal(cache.getQueryState(["paper-interaction", "", "id"])?.isInvalidated, true);
  assert.equal(cache.getQueryState(["topic-interaction", "b", "id"])?.isInvalidated, true);
  assert.deepEqual(cache.getQueryData(["topic-interaction", "b", "id"]), { marker: "b" });
  cache.clear();
});

test("personal writes and list reads carry an account precondition", async () => {
  const original = globalThis.fetch;
  const requests: { path: string; owner: string | null }[] = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ path: String(input), owner: new Headers(init?.headers).get("x-shenzhi-expected-user-id") });
    return new Response(JSON.stringify({ code: 0, data: { paper_id: "paper", liked: true, like_count: 1 } }));
  };
  try {
    await likePaper("paper", "a");
    await fetchMyLikes("a");
    await fetchMyCollectedPapers("a");
    await fetchMyTopicFollows("a");
    assert.equal(requests.length, 4);
    assert.ok(requests.every((request) => request.owner === "a"));
  } finally { globalThis.fetch = original; }
});

import test from "node:test";
import assert from "node:assert/strict";

import {
  invalidateKnowledgeOverviewCache,
  loadKnowledgeOverview,
  loadKnowledgeOverviewForGeneration,
} from "../../features/knowledge/lib/overview-cache.js";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((settle, fail) => {
    resolve = settle;
    reject = fail;
  });
  return { promise, resolve, reject };
}

test("knowledge overview reuses successful requests across dashboard mounts", async () => {
  invalidateKnowledgeOverviewCache();
  let overviewCalls = 0;
  let personalCalls = 0;
  const client = {
    overview: async () => {
      overviewCalls += 1;
      return { value: "overview" };
    },
    personalOverview: async () => {
      personalCalls += 1;
      return { value: "personal" };
    },
  } as never;

  await loadKnowledgeOverview(client);
  await loadKnowledgeOverview(client);

  assert.equal(overviewCalls, 1);
  assert.equal(personalCalls, 1);
  invalidateKnowledgeOverviewCache();
  await loadKnowledgeOverview(client);
  assert.equal(overviewCalls, 2);
  assert.equal(personalCalls, 2);
});

test("failed overview requests are retryable", async () => {
  invalidateKnowledgeOverviewCache();
  let attempts = 0;
  const client = {
    overview: async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("temporary failure");
      return { value: "overview" };
    },
    personalOverview: async () => ({ value: "personal" }),
  } as never;

  const first = await loadKnowledgeOverview(client);
  assert.equal(first[0].status, "rejected");
  const second = await loadKnowledgeOverview(client);
  assert.equal(second[0].status, "fulfilled");
  assert.equal(attempts, 2);
});

test("a stale identity request cannot overwrite the latest overview generation", async () => {
  invalidateKnowledgeOverviewCache();
  const publicA = deferred<{ value: string }>();
  const personalA = deferred<{ value: string }>();
  const publicB = deferred<{ value: string }>();
  const personalB = deferred<{ value: string }>();
  const publicRequests = [publicA.promise, publicB.promise];
  const personalRequests = [personalA.promise, personalB.promise];
  const client = {
    overview: async () => publicRequests.shift()!,
    personalOverview: async () => personalRequests.shift()!,
  } as never;

  let generation = 0;
  const rendered = { public: "", personal: "", error: false };
  const apply = async (identityKey: string) => {
    const requestGeneration = ++generation;
    const result = await loadKnowledgeOverviewForGeneration(
      client,
      identityKey,
      requestGeneration,
      () => generation,
    );
    if (!result) return;
    if (result[0].status === "fulfilled") {
      rendered.public = (result[0].value as unknown as { value: string }).value;
    } else rendered.error = true;
    if (result[1].status === "fulfilled") {
      rendered.personal = (result[1].value as unknown as { value: string }).value;
    }
  };

  const requestA = apply("anonymous");
  const requestB = apply("user-b");
  publicB.resolve({ value: "public-b" });
  personalB.resolve({ value: "personal-b" });
  await requestB;
  publicA.reject(new Error("stale anonymous failure"));
  personalA.resolve({ value: "personal-a" });
  await requestA;

  assert.deepEqual(rendered, {
    public: "public-b",
    personal: "personal-b",
    error: false,
  });
  invalidateKnowledgeOverviewCache();
});

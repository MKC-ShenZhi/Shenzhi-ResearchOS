import test from "node:test";
import assert from "node:assert/strict";

import { invalidateKnowledgeOverviewCache, loadKnowledgeOverview } from "../../features/knowledge/lib/overview-cache.js";

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

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fetchPaperInteraction, fetchTopicInteraction } from "../../clients/backend/interactions";

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

test("simultaneous card reads merge into one batched request", async () => {
  const previousFetch = globalThis.fetch;
  const requests: string[][] = [];
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(init?.body as string) as { paper_ids: string[] };
    requests.push(body.paper_ids);
    return jsonResponse({
      code: 0,
      data: {
        authenticated: false,
        user_id: null,
        items: body.paper_ids.map((paperId) => ({
          paper_id: paperId,
          collector_count: 3,
          like_count: 2,
          folder_ids: null,
          liked: null,
        })),
      },
    });
  };
  try {
    const states = await Promise.all([
      fetchPaperInteraction("", "paper:one"),
      fetchPaperInteraction("", "paper:two"),
      fetchPaperInteraction("", "paper:one"),
    ]);
    assert.deepEqual(requests, [["paper:one", "paper:two"]]);
    assert.equal(states[0].collectorCount, 3);
    assert.equal(states[1].likeCount, 2);
    assert.equal(states[0].folderIds, null);
    assert.equal(states[0].liked, null);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("topic cards share the same batched transport", async () => {
  const previousFetch = globalThis.fetch;
  const requests: string[][] = [];
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(init?.body as string) as { topic_ids: string[] };
    requests.push(body.topic_ids);
    return jsonResponse({
      code: 0,
      data: {
        authenticated: true,
        user_id: "user-a",
        items: body.topic_ids.map((topicId) => ({
          topic_id: topicId,
          follower_count: 2,
          is_following: topicId === "deep-learning",
        })),
      },
    });
  };
  try {
    const states = await Promise.all([
      fetchTopicInteraction("user-a", "deep-learning"),
      fetchTopicInteraction("user-a", "reinforcement-learning"),
    ]);
    assert.deepEqual(requests, [["deep-learning", "reinforcement-learning"]]);
    assert.equal(states[0].isFollowing, true);
    assert.equal(states[1].isFollowing, false);
    assert.equal(states[0].followerCount, 2);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("a response belonging to another account is never applied", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => jsonResponse({
    code: 0,
    data: {
      authenticated: true,
      user_id: "user-b",
      items: [{
        paper_id: "paper:one",
        collector_count: 1,
        like_count: 1,
        folder_ids: [1],
        liked: true,
      }],
    },
  });
  try {
    await assert.rejects(fetchPaperInteraction("user-a", "paper:one"), /所属账户已变化/);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("large result grids are split at the backend's 100-id limit", async () => {
  const previousFetch = globalThis.fetch;
  const sizes: number[] = [];
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(init?.body as string) as { paper_ids: string[] };
    sizes.push(body.paper_ids.length);
    return jsonResponse({
      code: 0,
      data: {
        authenticated: true,
        user_id: "user-a",
        items: body.paper_ids.map((paperId) => ({
          paper_id: paperId,
          collector_count: 0,
          like_count: 0,
          folder_ids: [],
          liked: false,
        })),
      },
    });
  };
  try {
    const states = await Promise.all(Array.from(
      { length: 101 },
      (_, index) => fetchPaperInteraction("user-a", `paper-${index}`),
    ));
    assert.equal(states.length, 101);
    assert.deepEqual(sizes, [100, 1]);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

const TOPIC_CARD = readFileSync("features/knowledge/topics/topic-card.tsx", "utf8");
const PAPER_CARD = readFileSync("features/search/components/paper-card.tsx", "utf8");
const RESULT_CARD = readFileSync("features/knowledge/search/components/result-card.tsx", "utf8");
const PICKER = readFileSync("features/knowledge/papers/components/collection-picker.tsx", "utf8");
const LIKE_BUTTON = readFileSync(
  "features/knowledge/interactions/components/paper-like-button.tsx",
  "utf8",
);
const FOLLOW_BUTTON = readFileSync(
  "features/knowledge/interactions/components/topic-follow-button.tsx",
  "utf8",
);
const PREFERENCES = readFileSync("stores/user-preferences.ts", "utf8");
const CACHE = readFileSync("features/knowledge/interactions/cache.ts", "utf8");
const SYNC = readFileSync("providers/interaction-sync.tsx", "utf8");

test("cards no longer read counts or personal state from browser storage", () => {
  for (const [name, source] of [["topic-card", TOPIC_CARD], ["paper-card", PAPER_CARD]] as const) {
    assert.doesNotMatch(source, /useUserPreferences/, name);
  }
  assert.doesNotMatch(TOPIC_CARD, /topic\.followersCount/);
  assert.match(TOPIC_CARD, /<TopicFollowButton/);
  assert.match(TOPIC_CARD, /<TopicFollowerCount/);
  assert.doesNotMatch(PAPER_CARD, /likedPapers|toggleLike/);
  assert.match(PAPER_CARD, /<PaperLikeButton/);
  assert.match(PAPER_CARD, /<PaperCollectorCount/);
  assert.match(RESULT_CARD, /<PaperCollectorCount/);
});

test("anonymous clicks open the existing login dialog instead of writing", () => {
  for (const [name, source] of [
    ["collection picker", PICKER],
    ["like button", LIKE_BUTTON],
    ["follow button", FOLLOW_BUTTON],
  ] as const) {
    assert.match(source, /openLogin\(/, name);
    assert.match(source, /!session/, name);
  }
  // 收藏在登录成功后仍需用户确认，不自动提交。
  assert.doesNotMatch(PICKER, /onSuccess: \(\) => void save/);
  assert.match(PICKER, /onSuccess: \(\) => changeOpen\(true\)/);
});

test("local topic/like/bookmark truth is removed and migrated away", () => {
  assert.doesNotMatch(PREFERENCES, /followedTopics\s*:/);
  assert.doesNotMatch(PREFERENCES, /likedPapers\s*:/);
  assert.doesNotMatch(PREFERENCES, /bookmarkedPapers\s*:/);
  assert.match(PREFERENCES, /delete state\.followedTopics/);
  assert.match(PREFERENCES, /delete state\.likedPapers/);
  assert.match(PREFERENCES, /delete state\.bookmarkedPapers/);
});

test("account switches drop other identities' personal interaction cache", () => {
  assert.match(CACHE, /removeQueries/);
  assert.match(CACHE, /owner !== "" && owner !== userId/);
  assert.match(SYNC, /BroadcastChannel/);
});

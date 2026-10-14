import assert from "node:assert/strict";
import test from "node:test";
import { fetchPaperReadStatus } from "../../clients/backend/read-status";

test("simultaneous card checks use one request and preserve paper IDs", async () => {
  const previousFetch = globalThis.fetch;
  const requests: string[][] = [];
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(init?.body as string) as { paper_ids: string[] };
    requests.push(body.paper_ids);
    return new Response(JSON.stringify({
      code: 0,
      data: { user_id: "user-a", read_paper_ids: ["paper:one"], reading_paper_ids: ["paper:two"] },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    const statuses = await Promise.all([
      fetchPaperReadStatus("user-a", "paper:one"),
      fetchPaperReadStatus("user-a", "paper:two"),
      fetchPaperReadStatus("user-a", "paper:one"),
    ]);
    assert.deepEqual(statuses, ["read", "reading", "read"]);
    assert.deepEqual(requests, [["paper:one", "paper:two"]]);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("a response from a different signed-in account is never used", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    code: 0,
    data: { user_id: "user-b", read_paper_ids: ["paper:one"], reading_paper_ids: [] },
  }), { status: 200, headers: { "Content-Type": "application/json" } });
  try {
    await assert.rejects(fetchPaperReadStatus("user-a", "paper:one"), /所属账户已变化/);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("large result grids are split at the backend's 100-paper limit", async () => {
  const previousFetch = globalThis.fetch;
  const sizes: number[] = [];
  globalThis.fetch = async (_input, init) => {
    const body = JSON.parse(init?.body as string) as { paper_ids: string[] };
    sizes.push(body.paper_ids.length);
    return new Response(JSON.stringify({
      code: 0,
      data: { user_id: "user-a", read_paper_ids: [], reading_paper_ids: [] },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    const statuses = await Promise.all(Array.from(
      { length: 101 }, (_, index) => fetchPaperReadStatus("user-a", `paper-${index}`),
    ));
    assert.equal(statuses.length, 101);
    assert.ok(statuses.every((status) => status === null));
    assert.deepEqual(sizes, [100, 1]);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

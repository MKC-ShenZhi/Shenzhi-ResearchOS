import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  BffKnowledgeClient,
  getKnowledgeClient,
  KnowledgeClientError,
  MockKnowledgeClient,
} from "../../clients/knowledge/index.js";
import { apiJson, ApiError } from "../../clients/backend/http.js";
import { paperHref, paperIdFromRouteParam } from "../../lib/navigation/paper";
import { knowledgeQueryRetry } from "../../features/knowledge/retry.js";

const SEARCH_PARAMS = {
  query: "graph neural network",
  topK: 20,
  yearFrom: 2021,
  yearTo: 2026,
  venue: ["AAAI"],
  author: ["Ada Lovelace"],
  keyword: ["graph"],
  subject: ["machine learning"],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function withFetch(
  implementation: typeof fetch,
  callback: () => Promise<void>,
): Promise<void> {
  const original = globalThis.fetch;
  globalThis.fetch = implementation;
  try {
    await callback();
  } finally {
    globalThis.fetch = original;
  }
}

test("BFF client unwraps the Search success envelope and preserves the request contract", async () => {
  const requests: Array<{ url: string; method: string; body: unknown }> = [];
  await withFetch(async (input, init) => {
    requests.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return jsonResponse({ code: 0, data: { results: [] } });
  }, async () => {
    const result = await new BffKnowledgeClient().search(SEARCH_PARAMS);
    assert.deepEqual(result, { results: [] });
  });

  assert.deepEqual(requests, [{
    url: "/api/v1/knowledge/search",
    method: "POST",
    body: SEARCH_PARAMS,
  }]);
});

test("BFF client requests Detail and Graph through same-origin routes", async () => {
  const requests: string[] = [];
  const rawPaperId = "paper:2025_findings_acl_1253_acl:012e17bab23d";
  const paperId = paperIdFromRouteParam(encodeURIComponent(rawPaperId));
  await withFetch(async (input) => {
    requests.push(String(input));
    if (requests.length === 1) {
      return jsonResponse({ code: 0, data: {
        id: paperId,
        title: "Paper",
        abstract: null,
        authors: [],
        year: null,
        venue: null,
        doi: null,
        pdfUrl: null,
        keywords: [],
        subjects: [],
        citationCount: null,
        referenceCount: null,
        provenance: { provider: "knowledge-base" },
      } });
    }
    return jsonResponse({ code: 0, data: {
      rootId: paperId,
      nodes: [],
      edges: [],
      provenance: { provider: "knowledge-base" },
    } });
  }, async () => {
    const client = new BffKnowledgeClient();
    const detail = await client.paper(paperId);
    const graph = await client.graph(paperId, 2);
    assert.equal(detail.id, paperId);
    assert.equal(graph.rootId, paperId);
  });

  assert.deepEqual(requests, [
    `/api/v1/knowledge/paper?paperId=${encodeURIComponent(paperId)}`,
    `/api/v1/knowledge/graph?paperId=${encodeURIComponent(paperId)}&depth=2`,
  ]);
  assert.ok(requests.every((request) => !request.includes("%253A")));
});

test("BFF client preserves formal Knowledge errors and request metadata", async () => {
  const cases = [
    ["NOT_FOUND", false, 404],
    ["TIMEOUT", true, 504],
    ["UPSTREAM_UNAVAILABLE", true, 503],
    ["RATE_LIMITED", true, 429],
    ["INVALID_ARGUMENT", false, 422],
    ["CONTRACT_VIOLATION", false, 502],
  ] as const;

  for (const [code, retryable, status] of cases) {
    await withFetch(async () => jsonResponse({
      code,
      message: "safe knowledge error",
      retryable,
      requestId: `request-${code.toLowerCase()}`,
    }, status), async () => {
      await assert.rejects(
        new BffKnowledgeClient().paper("paper:opaque"),
        (error: unknown) => {
          assert.ok(error instanceof KnowledgeClientError);
          assert.equal(error.code, code);
          assert.equal(error.message, "safe knowledge error");
          assert.equal(error.retryable, retryable);
          assert.equal(error.requestId, `request-${code.toLowerCase()}`);
          return true;
        },
      );
    });
  }
});

test("formal Knowledge errors preserve a nullable requestId", async () => {
  await withFetch(async () => jsonResponse({
    code: "NOT_FOUND",
    message: "safe knowledge error",
    retryable: false,
    requestId: null,
  }, 404), async () => {
    await assert.rejects(
      new BffKnowledgeClient().paper("paper:opaque"),
      (error: unknown) => {
        assert.ok(error instanceof KnowledgeClientError);
        assert.equal(error.code, "NOT_FOUND");
        assert.equal(error.retryable, false);
        assert.equal(error.requestId, null);
        return true;
      },
    );
  });
});

test("unknown formal errors normalize to UNKNOWN without losing safe metadata", async () => {
  await withFetch(async () => jsonResponse({
    code: "NEW_KNOWLEDGE_ERROR",
    message: "safe unknown error",
    retryable: true,
    requestId: "request-unknown",
  }, 500), async () => {
    await assert.rejects(
      new BffKnowledgeClient().paper("paper:opaque"),
      (error: unknown) => {
        assert.ok(error instanceof KnowledgeClientError);
        assert.equal(error.code, "UNKNOWN");
        assert.equal(error.retryable, true);
        assert.equal(error.requestId, "request-unknown");
        assert.equal(error.message, "safe unknown error");
        return true;
      },
    );
  });
});

test("malformed upstream-facing error text is not exposed to the browser", async () => {
  await withFetch(async () => new Response(
    "https://47.110.47.12 secret-token traceback",
    { status: 503 },
  ), async () => {
    await assert.rejects(
      new BffKnowledgeClient().paper("paper:opaque"),
      (error: unknown) => {
        assert.ok(error instanceof KnowledgeClientError);
        assert.doesNotMatch(error.message, /47\.110\.47\.12|secret-token|traceback/);
        return true;
      },
    );
  });
});

test("the default Knowledge client is BFF and Mock requires an explicit source", () => {
  const original = process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE;
  try {
    delete process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE;
    assert.ok(getKnowledgeClient() instanceof BffKnowledgeClient);
    process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE = "mock";
    assert.ok(getKnowledgeClient() instanceof MockKnowledgeClient);
    process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE = "unexpected-value";
    assert.ok(getKnowledgeClient() instanceof BffKnowledgeClient);
  } finally {
    if (original === undefined) delete process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE;
    else process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE = original;
  }
});

test("a failed BFF request stays an error and never falls back to Mock", async () => {
  const original = process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE;
  try {
    delete process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE;
    await withFetch(async () => jsonResponse({
      code: "UPSTREAM_UNAVAILABLE",
      message: "safe knowledge error",
      retryable: true,
      requestId: "request-upstream",
    }, 503), async () => {
      await assert.rejects(
        getKnowledgeClient().search(SEARCH_PARAMS),
        (error: unknown) => error instanceof KnowledgeClientError &&
          error.code === "UPSTREAM_UNAVAILABLE",
      );
    });
  } finally {
    if (original === undefined) delete process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE;
    else process.env.NEXT_PUBLIC_KNOWLEDGE_SOURCE = original;
  }
});

test("the generic numeric backend envelope remains compatible", async () => {
  await withFetch(async () => jsonResponse({ code: 0, data: { ok: true } }), async () => {
    assert.deepEqual(await apiJson<{ ok: boolean }>("/chat/config"), { ok: true });
  });
  await withFetch(async () => jsonResponse({ code: 21001, message: "legacy error" }, 400), async () => {
    await assert.rejects(
      apiJson("/chat/config"),
      (error: unknown) => error instanceof ApiError &&
        error.code === 21001 &&
        error.message === "legacy error",
    );
  });
});

test("Knowledge retry policy retries only retryable failures once", () => {
  assert.equal(
    knowledgeQueryRetry(0, new KnowledgeClientError("TIMEOUT", "timeout", { retryable: true })),
    true,
  );
  assert.equal(
    knowledgeQueryRetry(1, new KnowledgeClientError("TIMEOUT", "timeout", { retryable: true })),
    false,
  );
  assert.equal(
    knowledgeQueryRetry(0, new KnowledgeClientError("NOT_FOUND", "missing")),
    false,
  );
  assert.equal(
    knowledgeQueryRetry(0, new KnowledgeClientError("UNKNOWN", "unknown", { retryable: true })),
    true,
  );
  assert.equal(
    knowledgeQueryRetry(1, new KnowledgeClientError("UNKNOWN", "unknown", { retryable: true })),
    false,
  );
});

test("paper route boundary restores the ACL opaque ID after one path encoding", () => {
  const logicalId = "paper:2025_findings_acl_1253_acl:012e17bab23d";
  const href = paperHref(logicalId);
  const pathSegment = new URL(href, "https://local.test").pathname.slice("/papers/".length);

  assert.equal(pathSegment, "paper%3A2025_findings_acl_1253_acl%3A012e17bab23d");
  assert.equal(paperIdFromRouteParam(pathSegment), logicalId);
});

test("paper route boundary decodes exactly one layer and preserves a literal percent escape", () => {
  const logicalId = "paper:abc%2Fxyz";
  const href = paperHref(logicalId);
  const pathSegment = new URL(href, "https://local.test").pathname.slice("/papers/".length);

  assert.equal(pathSegment, "paper%3Aabc%252Fxyz");
  assert.equal(paperIdFromRouteParam(pathSegment), logicalId);
});

test("one decoded logical ID becomes one encoded BFF query value", async () => {
  const logicalId = "paper:abc:def";
  const paperId = logicalId;
  const requests: string[] = [];

  await withFetch(async (input) => {
    requests.push(String(input));
    return jsonResponse({ code: 0, data: { id: logicalId } });
  }, async () => {
    await new BffKnowledgeClient().paper(paperId);
  });

  const expectedQuery = new URLSearchParams({ paperId: logicalId }).toString();
  assert.equal(expectedQuery, "paperId=paper%3Aabc%3Adef");
  assert.deepEqual(requests, [`/api/v1/knowledge/paper?${expectedQuery}`]);
  assert.doesNotMatch(requests[0], /%253A/);
});

test("all paper routes decode their path segment at the business boundary exactly once", () => {
  for (const path of ["app/knowledge/search/[paperId]/page.tsx", "app/knowledge/search/[paperId]/graph/page.tsx", "app/papers/[id]/page.tsx", "app/papers/[id]/graph/page.tsx"]) {
    const source = readFileSync(path, "utf8");
    assert.equal((source.match(/paperIdFromRouteParam\s*\(/g) ?? []).length, 1);
    assert.doesNotMatch(source, /decodeURIComponent/);
  }
});

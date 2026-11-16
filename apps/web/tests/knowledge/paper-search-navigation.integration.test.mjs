import assert from "node:assert/strict";
import test from "node:test";

// Run against `next build` + `next start`; dev rendering cannot catch this bug.
const origin = process.env.PAPER_SEARCH_TEST_ORIGIN;
const options = { skip: !origin && "Set PAPER_SEARCH_TEST_ORIGIN to a production test server" };
const queries = [
  "mode=conference&conference=AAAI&year=2026",
  "mode=conference&conference=AAAI&year=2022",
  "mode=conference&conference=ICML&year=2025&page=2",
  "mode=keyword&q=graph&page=2",
];

function initialPayload(html) {
  const chunks = [...html.matchAll(/self\.__next_f\.push\(([^<]+)\)<\/script>/g)]
    .map((match) => JSON.parse(match[1]))
    .filter((chunk) => chunk[0] === 1)
    .map((chunk) => chunk[1])
    .join("");
  return rootPayload(chunks);
}

function rootPayload(flight) {
  // A length-delimited Flight text row can end immediately before row 0.
  const row = flight.match(/0:(\{[^\n]*\})/);
  assert.ok(row, "Expected the production App Router root Flight payload");
  const payload = JSON.parse(row[1]);
  assert.ok(Array.isArray(payload.f));
  return payload;
}

function assertRequestedQuery(payload, query) {
  assert.equal(typeof payload.q, "string");
  assert.deepEqual(
    [...new URLSearchParams(payload.q)].sort(),
    [...new URLSearchParams(query)].sort(),
    "Rendered search must match the request, not seed an empty-search cache entry",
  );
}

test("production paper-library documents retain each requested query in initial Flight", options, async () => {
  for (const query of queries) {
    const response = await fetch(new URL(`/knowledge/search?${query}`, origin), {
      signal: AbortSignal.timeout(15_000),
    });
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /text\/html/);
    assert.match(response.headers.get("cache-control") ?? "", /no-store/);
    assertRequestedQuery(initialPayload(await response.text()), query);
  }
});

test("production RSC navigations retain new conference, year, page and mode queries", options, async () => {
  for (const query of queries) {
    const response = await fetch(new URL(`/knowledge/search?${query}`, origin), {
      headers: { RSC: "1" },
      signal: AbortSignal.timeout(15_000),
    });
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /text\/x-component/);
    assertRequestedQuery(rootPayload(await response.text()), query);
  }
});

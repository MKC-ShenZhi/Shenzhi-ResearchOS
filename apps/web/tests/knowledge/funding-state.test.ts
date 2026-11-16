import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFundingUrl,
  readFundingUrlState,
} from "../../features/knowledge/funding/funding-url-state.js";

test("Funding URL state reads the search query and opaque Funding ID", () => {
  const state = readFundingUrlState(
    new URLSearchParams("q=Google%20Research&funding=funding%3Agoogle_research"),
  );

  assert.deepEqual(state, {
    query: "Google Research",
    fundingId: "funding:google_research",
  });
});

test("Funding URL state replaces q and funding without parsing the opaque ID", () => {
  const current = new URLSearchParams("q=old&funding=old&view=compact");

  assert.equal(
    buildFundingUrl(current, "Google Research", "funding:google_research"),
    "/knowledge/funding?q=Google+Research&funding=funding%3Agoogle_research&view=compact",
  );
  assert.equal(
    buildFundingUrl(current, "", null),
    "/knowledge/funding?view=compact",
  );
});

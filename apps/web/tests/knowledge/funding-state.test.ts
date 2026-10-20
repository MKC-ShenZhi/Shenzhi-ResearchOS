import assert from "node:assert/strict";
import test from "node:test";
import { getFundCardMetadata } from "../../features/knowledge/funding/fund-card-mock-data.js";

import {
  buildFundingUrl,
  fundingDetailHref,
  fundingLibraryHref,
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

test("Fund cards link to their own detail with real name and return query", () => {
  assert.equal(
    fundingDetailHref("funding:nsf/1553815", "CAREER: Surface Texturing", "glass"),
    "/knowledge/funding/funding%3Ansf%2F1553815?name=CAREER%3A+Surface+Texturing&q=glass",
  );
});

test("Fund detail returns to the library search", () => {
  assert.equal(fundingLibraryHref("glass"), "/knowledge/funding?q=glass");
  assert.equal(fundingLibraryHref(""), "/knowledge/funding");
});

test("Fund card metadata maps stable IDs to stable mock templates", () => {
  const first = getFundCardMetadata("fund-1");
  const next = getFundCardMetadata("fund-2");

  assert.deepEqual(first, {
    agencyAbbreviation: "NSF",
    agencyName: "National Science Foundation",
    projectType: "CAREER",
    shortDescription: "结合精密加工与表面织构技术，改善微尺度器件的性能表现。",
    principalInvestigator: "Maya Chen",
    hostInstitution: "Oklahoma State University",
    period: "2016–2021",
    fundingAmount: "$500,000",
  });
  assert.equal(first.principalInvestigator, "Maya Chen");
  assert.equal(next.principalInvestigator, "Daniel Kim");
  assert.deepEqual(first, getFundCardMetadata("fund-1"));
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

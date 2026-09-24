import assert from "node:assert/strict";
import test from "node:test";
import {
  comingSoonRedirectPath,
  isUnavailableFeatureHref,
  isUnavailableFeatureRoute,
} from "../../lib/feature-availability";

test("keeps currently released research routes available", () => {
  const availableRoutes = [
    "/",
    "/knowledge",
    "/knowledge/search",
    "/knowledge/papers",
    "/knowledge/scholars",
    "/knowledge/topics",
    "/knowledge/funding",
    "/papers/paper-1",
    "/papers/paper-1/graph",
  ];

  for (const pathname of availableRoutes) {
    assert.equal(isUnavailableFeatureRoute(pathname), false, pathname);
  }
});

test("blocks only the knowledge overview graph route", () => {
  assert.equal(isUnavailableFeatureHref("/knowledge/graph"), true);
  assert.equal(isUnavailableFeatureHref("/papers/paper-1/graph"), false);
  assert.equal(isUnavailableFeatureHref("/knowledge/graph-preview"), false);
});

test("blocks projects and submit routes at every depth", () => {
  for (const href of [
    "/projects",
    "/projects/demo",
    "/projects/demo/settings",
    "/submit",
    "/submit/journals",
    "/submit/journals/demo",
  ]) {
    assert.equal(isUnavailableFeatureHref(href), true, href);
  }

  assert.equal(isUnavailableFeatureHref("/projects-archive"), false);
  assert.equal(isUnavailableFeatureHref("/submission-guide"), false);
});

test("allows only the formal Agent Session Chat route", () => {
  assert.equal(isUnavailableFeatureHref("/agents"), true);
  assert.equal(isUnavailableFeatureHref("/agents?session="), true);
  assert.equal(isUnavailableFeatureHref("/agents?session=session-1"), false);
  assert.equal(
    isUnavailableFeatureHref("/agents?session=opaque%2Fid&launch=launch-1"),
    false,
  );

  for (const href of [
    "/agents/ask?session=session-1",
    "/agents/deep-search",
    "/agents/deep-research",
    "/agents/deep-research/session-1",
    "/agents/auto-research",
    "/agents/auto-research/session-1",
  ]) {
    assert.equal(isUnavailableFeatureHref(href), true, href);
  }
});

test("builds a one-time coming-soon notice redirect", () => {
  assert.equal(comingSoonRedirectPath(), "/?notice=coming-soon");
});

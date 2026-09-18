import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import test from "node:test";

import {
  extractArxivId,
  getPaperThumbnailUrl,
} from "../../lib/paper-thumbnail.js";

const THUMBNAIL_SOURCE = readFileSync(
  "components/common/paper-thumbnail.tsx",
  "utf8",
);
const FALLBACK_PATH = "public/images/papers/paper-thumbnail-fallback.webp";

test("paper thumbnail falls back for missing or failed sources without retrying the fallback", () => {
  assert.match(
    THUMBNAIL_SOURCE,
    /normalizedSrc && failedSrc !== normalizedSrc[\s\S]*?PAPER_THUMBNAIL_FALLBACK_SRC/,
  );
  assert.match(
    THUMBNAIL_SOURCE,
    /if \(imageSrc !== PAPER_THUMBNAIL_FALLBACK_SRC\)[\s\S]*?setFailedSrc\(imageSrc\)/,
  );
  assert.match(THUMBNAIL_SOURCE, /className="object-cover"/);
});

test("paper thumbnail fallback is a lightweight WebP asset", () => {
  const fallback = readFileSync(FALLBACK_PATH);

  assert.equal(fallback.subarray(0, 4).toString("ascii"), "RIFF");
  assert.equal(fallback.subarray(8, 12).toString("ascii"), "WEBP");
  assert.ok(statSync(FALLBACK_PATH).size < 50 * 1024);
});

test("extractArxivId only adapts supported modern arXiv paper ids", () => {
  assert.equal(extractArxivId("paper:2602.04284v2"), "2602.04284v2");
  assert.equal(extractArxivId("paper:2602.04284"), "2602.04284");
  assert.equal(extractArxivId("paper:2602.1234v1"), "2602.1234v1");
  assert.equal(extractArxivId("paper:17203_aaai:911ff38f19e8"), null);
});

test("getPaperThumbnailUrl honors the public feature flag", () => {
  const originalValue = process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED;

  try {
    process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = "false";
    assert.equal(getPaperThumbnailUrl("paper:2602.04284v2"), null);

    process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = "true";
    assert.equal(
      getPaperThumbnailUrl("paper:2602.04284v2"),
      "/api/paper-thumbnail/2602.04284v2",
    );
    assert.equal(
      getPaperThumbnailUrl("paper:17203_aaai:911ff38f19e8"),
      null,
    );
  } finally {
    if (originalValue === undefined) {
      delete process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED;
    } else {
      process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = originalValue;
    }
  }
});

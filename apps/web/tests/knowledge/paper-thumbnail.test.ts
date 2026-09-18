import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import test from "node:test";

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

import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { GET } from "../../app/api/paper-thumbnail/[arxivId]/route.js";

test("paper images reuse fresh bytes, revalidate unchanged files and invalidate replaced files", async () => {
  const originalDirectory = process.cwd();
  const directory = await mkdtemp(join(tmpdir(), "shenzhi-image-cache-"));
  const imageDirectory = join(directory, "data", "paper-thumbnails");
  const imagePath = join(imageDirectory, "2602.04284v2.png");
  const params = { params: Promise.resolve({ arxivId: "2602.04284v2" }) };
  const url = "http://localhost/api/paper-thumbnail/2602.04284v2";

  try {
    await mkdir(imageDirectory, { recursive: true });
    await writeFile(imagePath, "original image bytes");
    process.chdir(directory);

    const first = await GET(new Request(url), params);
    assert.equal(first.status, 200);
    assert.equal(await first.text(), "original image bytes");
    assert.equal(first.headers.get("Content-Type"), "image/png");
    assert.match(first.headers.get("Cache-Control") ?? "", /public, max-age=3600/);
    const etag = first.headers.get("ETag");
    assert.ok(etag);

    const cached = await GET(new Request(url, { headers: { "If-None-Match": `"other", ${etag}` } }), params);
    assert.equal(cached.status, 304);
    assert.equal(await cached.text(), "");
    assert.equal(cached.headers.get("ETag"), etag);

    await writeFile(imagePath, "replacement image with different bytes");
    const replaced = await GET(new Request(url, { headers: { "If-None-Match": etag } }), params);
    assert.equal(replaced.status, 200);
    assert.notEqual(replaced.headers.get("ETag"), etag);
    assert.equal(await replaced.text(), "replacement image with different bytes");

    const missing = await GET(new Request(url), { params: Promise.resolve({ arxivId: "2602.99999" }) });
    assert.equal(missing.status, 404);
    assert.equal(missing.headers.get("Cache-Control"), null);
    const invalid = await GET(new Request(url), { params: Promise.resolve({ arxivId: "../2602.04284v2" }) });
    assert.equal(invalid.status, 404);
  } finally {
    process.chdir(originalDirectory);
    await rm(directory, { recursive: true, force: true });
  }
});

import assert from "node:assert/strict";
import test from "node:test";

import { GET } from "../../app/api/paper-images/[...path]/route.js";
import { getKnowledgeBaseConfig } from "../../config/knowledge.js";

const request = (path: string[], headers?: HeadersInit) => GET(
  new Request("https://shenzhi.test/api/paper-images/CVPR_2026/paper.png?url=http://untrusted.test/", { headers }),
  { params: Promise.resolve({ path }) },
);

async function withProxy(
  implementation: typeof fetch,
  callback: () => Promise<void>,
  base: string | undefined = "https://knowledge.test/",
) {
  const originalFetch = globalThis.fetch;
  const originalBase = process.env.KNOWLEDGE_BASE_API_URL;
  const originalTimeout = process.env.KNOWLEDGE_BASE_TIMEOUT_SEC;
  globalThis.fetch = implementation;
  if (base === undefined) delete process.env.KNOWLEDGE_BASE_API_URL;
  else process.env.KNOWLEDGE_BASE_API_URL = base;
  delete process.env.KNOWLEDGE_BASE_TIMEOUT_SEC;
  try { await callback(); }
  finally {
    globalThis.fetch = originalFetch;
    if (originalBase === undefined) delete process.env.KNOWLEDGE_BASE_API_URL;
    else process.env.KNOWLEDGE_BASE_API_URL = originalBase;
    if (originalTimeout === undefined) delete process.env.KNOWLEDGE_BASE_TIMEOUT_SEC;
    else process.env.KNOWLEDGE_BASE_TIMEOUT_SEC = originalTimeout;
  }
}

test("proxy uses only the configured Knowledge base and forwards exact image bytes/MIME", async () => {
  for (const base of ["https://knowledge.test", "https://knowledge.test/", " https://knowledge.test/// "]) {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    await withProxy(async (url, init) => {
      calls.push({ url: String(url), init });
      const extension = String(url).split(".").pop()!.toLowerCase();
      const mime = extension === "png" ? "image/png" : extension === "webp" ? "image/webp" : "image/jpeg";
      return new Response(new Uint8Array([0, 1, 128, 255]), { headers: {
        "Content-Type": `${mime}; charset=binary`,
        "Cache-Control": "max-age=604800",
        "ETag": '"nginx-tag"',
        "Last-Modified": "Wed, 21 Oct 2026 00:00:00 GMT",
        "Set-Cookie": "must-not-leak=1", "Server": "nginx", "Location": "http://private.test/",
        "Content-Encoding": "gzip", "Content-Length": "9999",
      } });
    }, async () => {
      for (const path of [
        ["CVPR_2026", "2605.05077v2.png"], ["ICLR_2026", "2506.10941.PNG"],
        ["ECCV_2026", "2607.00409v1.webp"], ["pdf_backfill_2026", "4640138e89cd36ec780b.jpg"],
        ["ASPLOS_2026", "10.1145_3779212.3790216_minimal.jpeg"],
      ]) {
        const response = await request(path, { Cookie: "session=secret", Authorization: "Bearer secret", Range: "bytes=0-1" });
        assert.equal(response.status, 200);
        assert.deepEqual(new Uint8Array(await response.arrayBuffer()), new Uint8Array([0, 1, 128, 255]));
        assert.equal(response.headers.get("Cache-Control"), "max-age=604800");
        assert.equal(response.headers.get("ETag"), '"nginx-tag"');
        assert.equal(response.headers.get("Last-Modified"), "Wed, 21 Oct 2026 00:00:00 GMT");
        assert.equal(response.headers.get("X-Content-Type-Options"), "nosniff");
        const call = calls[calls.length - 1];
        assert.equal(call.url, `https://knowledge.test/images/${path.join("/")}`);
        assert.equal(call.init?.redirect, "manual");
        assert.equal(call.init?.cache, "no-store");
        assert.ok(call.init?.signal instanceof AbortSignal);
        const forwarded = new Headers(call.init?.headers);
        assert.equal(forwarded.get("Accept"), response.headers.get("Content-Type"));
        for (const name of ["cookie", "authorization", "range", "host"]) assert.equal(forwarded.get(name), null);
        for (const name of ["set-cookie", "server", "location", "content-encoding", "content-length"]) {
          assert.equal(response.headers.get(name), null);
        }
      }
    }, base);
  }
});

test("invalid paths never make an upstream request", async () => {
  await withProxy(async () => { throw new Error("must not fetch"); }, async () => {
    for (const path of [
      [], ["..", "secret.png"], [".", "secret.png"], ["/tmp/secret.png"],
      ["CVPR_2026/paper.png"], ["CVPR_2026\\paper.png"], ["%2e%2e", "secret.png"],
      ["%252e%252e", "secret.png"], ["CVPR_2026", "%2fsecret.png"],
      ["CVPR_2026", "paper.png\0"], ["CVPR_2026", "paper.svg"],
      ["CVPR_2026", "paper.png?x"], ["CVPR_2026", "paper.png#x"],
      ["https:", "evil.test", "secret.png"], ["//evil.test/secret.png"],
    ]) {
      const response = await request(path);
      assert.equal(response.status, 404, JSON.stringify(path));
      assert.equal(response.headers.get("Cache-Control"), "no-store");
    }
  });
});

test("missing/invalid server configuration is a safe 503 without fetching", async () => {
  let calls = 0;
  for (const base of ["", " ", "not-a-url", "file:///tmp/", "ftp://knowledge.test/",
    "http://user:secret@knowledge.test/", "http://knowledge.test/?url=other", "http://knowledge.test/#hash"]) {
    await withProxy(async () => { calls++; throw new Error("must not fetch"); }, async () => {
      const response = await request(["CVPR_2026", "paper.png"]);
      assert.equal(response.status, 503, String(base));
      assert.equal(await response.text(), "");
      assert.equal(response.headers.get("Cache-Control"), "no-store");
    }, base);
  }
  await withProxy(async () => { calls++; throw new Error("must not fetch"); }, async () => {
    delete process.env.KNOWLEDGE_BASE_API_URL;
    assert.equal((await request(["CVPR_2026", "paper.png"])).status, 503);
  });
  assert.equal(calls, 0);
});

test("conditional cache requests preserve upstream ETag, Last-Modified and empty 304 responses", async () => {
  await withProxy(async (_url, init) => {
    const headers = new Headers(init?.headers);
    assert.equal(headers.get("If-None-Match"), 'W/"nginx-tag"');
    assert.equal(headers.get("If-Modified-Since"), "Wed, 21 Oct 2026 00:00:00 GMT");
    return new Response(null, { status: 304, headers: {
      ETag: '"nginx-tag"', "Cache-Control": "max-age=604800",
      "Last-Modified": "Wed, 21 Oct 2026 00:00:00 GMT",
    } });
  }, async () => {
    const response = await request(["CVPR_2026", "paper.png"], {
      "If-None-Match": 'W/"nginx-tag"', "If-Modified-Since": "Wed, 21 Oct 2026 00:00:00 GMT",
    });
    assert.equal(response.status, 304);
    assert.equal(await response.text(), "");
    assert.equal(response.headers.get("ETag"), '"nginx-tag"');
    assert.equal(response.headers.get("Cache-Control"), "max-age=604800");
    assert.equal(response.headers.get("Content-Type"), null);
  });
});

test("proxy rejects all redirects, upstream errors, non-image MIME and extension mismatches", async () => {
  for (const [status, mime, expected] of [
    [301, "image/png", 502], [302, "image/png", 502], [307, "image/png", 502], [308, "image/png", 502],
    [304, null, 502], [404, "text/html", 404], [410, "text/html", 404], [500, "text/html", 502],
    [403, "text/html", 502], [429, "text/html", 502], [206, "image/png", 502],
    [200, "text/html", 502], [200, "image/svg+xml", 502], [200, "image/jpeg", 502], [200, null, 502],
  ] as const) {
    let calls = 0;
    await withProxy(async () => {
      calls++;
      return new Response(status === 304 ? null : "unsafe bytes", { status, headers: {
        ...(mime ? { "Content-Type": mime } : {}), Location: "http://untrusted.test/secret.png",
      } });
    }, async () => {
      const response = await request(["CVPR_2026", "paper.png"]);
      assert.equal(response.status, expected, `${status} ${mime}`);
      assert.equal(calls, 1);
      assert.equal(await response.text(), "");
      assert.equal(response.headers.get("Location"), null);
      assert.equal(response.headers.get("Cache-Control"), "no-store");
    });
  }
});

test("network and body-read failures become 502; header/body timeouts become 504", async () => {
  for (const failure of ["network", "body", "headers-timeout", "body-timeout"]) {
    await withProxy(async (_url, init) => {
      if (failure === "network") throw new TypeError("upstream unavailable");
      if (failure === "body") return new Response(new ReadableStream({
        start(controller) { controller.error(new Error("body read failed")); },
      }), { headers: { "Content-Type": "image/png" } });
      assert.ok(init?.signal);
      const signal = init.signal;
      const aborted = new Promise<never>((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      });
      if (failure === "headers-timeout") return await aborted;
      return new Response(new ReadableStream({
        start(controller) { void aborted.catch((error: unknown) => controller.error(error)); },
      }), { headers: { "Content-Type": "image/png" } });
    }, async () => {
      process.env.KNOWLEDGE_BASE_TIMEOUT_SEC = "0.01";
      // AbortSignal.timeout uses an unref timer; keep this isolated test alive.
      const keepAlive = setTimeout(() => {}, 1000);
      try {
        const response = await request(["CVPR_2026", "paper.png"]);
        assert.equal(response.status, failure.endsWith("timeout") ? 504 : 502);
        assert.equal(await response.text(), "");
        assert.equal(response.headers.get("Cache-Control"), "no-store");
      } finally { clearTimeout(keepAlive); }
    });
  }
});

test("runtime config reuses the shared URL/timeout names and safely defaults invalid timeouts", async () => {
  await withProxy(async () => new Response("png", { headers: { "Content-Type": "image/png" } }), async () => {
    for (const value of [undefined, "", "bad", "0", "-1", "Infinity", "2147483.648", "1e100"]) {
      if (value === undefined) delete process.env.KNOWLEDGE_BASE_TIMEOUT_SEC;
      else process.env.KNOWLEDGE_BASE_TIMEOUT_SEC = value;
      assert.equal(getKnowledgeBaseConfig()?.timeoutMs, 30_000);
    }
    process.env.KNOWLEDGE_BASE_TIMEOUT_SEC = "1.5";
    assert.equal(getKnowledgeBaseConfig()?.timeoutMs, 1500);
    const response = await request(["CVPR_2026", "paper.png"]);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Cache-Control"), "public, max-age=3600, must-revalidate");
  });
});

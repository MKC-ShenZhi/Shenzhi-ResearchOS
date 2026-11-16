import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";
import { readForwardedBody } from "../../clients/backend/forward";

test("empty interaction writes have no streaming body", async () => {
  const request = new Request("http://localhost/like", { method: "PUT", headers: { "content-length": "0" } });
  assert.equal(await readForwardedBody(request), undefined);
});

test("JSON writes remain replayable so a backend 401 reaches the caller", async () => {
  const server = createServer((request, response) => {
    request.resume();
    response.writeHead(401, { "content-type": "application/json" });
    response.end(JSON.stringify({ code: 10001, message: "请登录后使用此功能" }));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const request = new Request(`http://127.0.0.1:${address.port}/like`, {
      method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ folder_ids: [1] }),
    });
    const body = await readForwardedBody(request);
    assert.equal(body, '{"folder_ids":[1]}');
    const response = await fetch(request.url, { method: "PUT", body, redirect: "manual" });
    assert.equal(response.status, 401);
    assert.equal((await response.json()).code, 10001);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("binary uploads keep their streaming transport", async () => {
  const request = new Request("http://localhost/upload", { method: "POST", headers: { "content-type": "application/pdf" }, body: new Uint8Array([1, 2, 3]) });
  assert.equal(await readForwardedBody(request), request.body);
});

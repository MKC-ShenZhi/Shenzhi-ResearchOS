import assert from "node:assert/strict";
import test from "node:test";
import { POST } from "../../app/api/payment-notifications/[channel]/route";
import { backendConfig } from "../../config/backend";

test("dedicated payment callback preserves original bytes and signature headers only", async (t) => {
  const previous = backendConfig.url;
  backendConfig.url = "http://backend.test";
  t.after(() => { backendConfig.url = previous; });
  const body = '{ "resource": "signed body" }\n';
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.equal(url, "http://backend.test/api/v1/payment-webhooks/wechat");
    assert.equal(new TextDecoder().decode(init.body as ArrayBuffer), body);
    const headers = new Headers(init.headers);
    assert.equal(headers.get("wechatpay-signature"), "signed-test");
    assert.equal(headers.get("wechatpay-timestamp"), "123");
    for (const name of ["cookie", "authorization", "x-shenzhi-user-id", "x-shenzhi-bff-secret"]) assert.equal(headers.get(name), null);
    return new Response(null, { status: 204 });
  });
  const request = new Request("http://web.test/api/payment-notifications/wechat", { method: "POST", body,
    headers: { "content-type": "application/json", "wechatpay-signature": "signed-test", "wechatpay-timestamp": "123",
      "cookie": "session=private", "authorization": "Bearer untrusted", "x-shenzhi-user-id": "forged" } });
  const result = await POST(request, { params: Promise.resolve({ channel: "wechat" }) });
  assert.equal(result.status, 204);
});

test("callback rejects arbitrary destination channels", async () => {
  const response = await POST(new Request("http://web.test/api/payment-notifications/admin-console", { method: "POST" }),
    { params: Promise.resolve({ channel: "admin-console" }) });
  assert.equal(response.status, 404);
});

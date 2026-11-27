import { backendConfig } from "../../../../config/backend";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Dedicated raw callback transport. No user session or general BFF header changes. */
export async function POST(request: Request, context: { params: Promise<{ channel: string }> }) {
  const { channel } = await context.params;
  if (channel !== "wechat" && channel !== "alipay") return new Response(null, { status: 404 });
  if (!backendConfig.url) return new Response(null, { status: 503 });
  const headers = new Headers();
  for (const name of ["content-type", "wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial", "wechatpay-signature-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const response = await fetch(`${backendConfig.url.replace(/\/$/, "")}/api/v1/payment-webhooks/${channel}`, {
      method: "POST", headers, body: await request.arrayBuffer(), cache: "no-store",
      redirect: "manual", signal: AbortSignal.timeout(30000),
    });
    return new Response(response.body, { status: response.status, headers: {
      "Content-Type": response.headers.get("content-type") ?? "text/plain", "Cache-Control": "no-store",
    } });
  } catch {
    return new Response(null, { status: 502 });
  }
}

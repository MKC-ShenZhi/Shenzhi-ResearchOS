import { NextRequest, NextResponse } from "next/server";

import { backendConfig, backendConnectionIsAllowed } from "@/config/backend";
import {
  attachMigrationIdentity,
  resolveBackendIdentity,
} from "@/clients/backend/identity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ANONYMOUS_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Preview only: it never changes ownership or returns conversation content. */
export async function GET(request: NextRequest) {
  const empty = () => NextResponse.json({ code: 0, data: { count: 0 } });
  if (!backendConfig.url || !backendConnectionIsAllowed(backendConfig)) {
    return NextResponse.json({ code: 20004, message: "历史服务不可用" }, { status: 503 });
  }
  try {
    const identity = await resolveBackendIdentity(request.headers);
    if (identity.kind !== "authenticated") {
      return NextResponse.json({ code: 10001, message: "请先登录" }, { status: 401 });
    }
    const anonymousId = request.cookies.get("shenzhi-chat-anon")?.value;
    if (!anonymousId || !ANONYMOUS_ID.test(anonymousId)) return empty();
    const headers = new Headers({ "X-ShenZhi-Anonymous-Id": anonymousId });
    if (backendConfig.secret) headers.set("X-ShenZhi-Bff-Secret", backendConfig.secret);
    const upstream = await fetch(`${backendConfig.url.replace(/\/$/, "")}/api/v1/chat/sessions`, {
      headers, cache: "no-store", signal: request.signal,
    });
    const body = await upstream.json();
    if (!upstream.ok || body.code !== 0 || !Array.isArray(body.data?.sessions)) {
      throw new Error("Invalid history response");
    }
    return NextResponse.json({ code: 0, data: {
      count: body.data.ephemeral === false ? body.data.sessions.length : 0,
    } });
  } catch {
    return NextResponse.json({ code: 20004, message: "暂时无法检查匿名历史" }, { status: 503 });
  }
}

export async function POST(request: NextRequest) {
  if (!backendConfig.url || !backendConnectionIsAllowed(backendConfig)) {
    return NextResponse.json(
      { code: 20004, message: "匿名会话归属服务未配置" },
      { status: 503 },
    );
  }

  let identity;
  try {
    identity = await resolveBackendIdentity(request.headers);
  } catch {
    return NextResponse.json(
      { code: 10001, message: "鉴权服务异常，请稍后重试" },
      { status: 503 },
    );
  }
  if (identity.kind !== "authenticated") {
    return NextResponse.json(
      { code: 10001, message: "请登录后认领匿名会话" },
      { status: 401 },
    );
  }

  const anonymousId = request.cookies.get("shenzhi-chat-anon")?.value;
  if (!anonymousId || !ANONYMOUS_ID.test(anonymousId)) {
    return NextResponse.json({
      code: 0,
      data: { moved_count: 0, skipped_streaming_count: 0, durable: true },
    });
  }

  const headers = new Headers();
  attachMigrationIdentity(headers, identity.userId, anonymousId);
  if (backendConfig.secret) {
    headers.set("X-ShenZhi-Bff-Secret", backendConfig.secret);
  }

  try {
    const upstream = await fetch(
      `${backendConfig.url.replace(/\/$/, "")}/api/v1/chat/anonymous-claim`,
      {
        method: "POST",
        headers,
        cache: "no-store",
        signal: request.signal,
      },
    );
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      { code: 20004, message: "无法连接匿名会话归属服务" },
      { status: 503 },
    );
  }
}

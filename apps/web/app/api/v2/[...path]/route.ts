import { NextRequest, NextResponse } from "next/server";

import { backendConfig, backendConnectionIsAllowed } from "@/config/backend";
import { forwardToBusinessBackend } from "@/clients/backend/forward";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

async function handle(req: NextRequest, ctx: Ctx) {
  const base = backendConfig.url;
  if (!base) {
    return NextResponse.json({ code: 20004, message: "生成服务未配置" }, { status: 503 });
  }
  if (!backendConnectionIsAllowed(backendConfig)) {
    return NextResponse.json({ code: 10001, message: "后端调用凭据未配置" }, { status: 503 });
  }

  const path = (await ctx.params).path ?? [];
  // forward.ts owns decoded path validation and public/internal isolation.
  return forwardToBusinessBackend(req, base, path, "v2");
}

export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;

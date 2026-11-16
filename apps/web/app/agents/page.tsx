import { Suspense } from "react";
import { AgentHomePage } from "@/features/agent-chat/agent-home-page";
import { ShenzhiAiPage } from "@/features/agent-chat/shenzhi-ai-page";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ session?: string }>;
}) {
  if (!(await searchParams).session) return <AgentHomePage />;
  return <Suspense fallback={null}><ShenzhiAiPage /></Suspense>;
}

import { Suspense } from "react";
import { redirect } from "next/navigation";
import { ShenzhiAiPage } from "@/features/agent-chat/shenzhi-ai-page";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ session?: string }>;
}) {
  if (!(await searchParams).session) redirect("/");
  return <Suspense fallback={null}><ShenzhiAiPage /></Suspense>;
}

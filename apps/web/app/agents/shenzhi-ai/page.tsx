import type { Metadata } from "next";

import { ShenzhiAiPage } from "@/features/agent-chat/shenzhi-ai-page";

export const metadata: Metadata = { title: "ShenzhiAi · 深知" };

export default function Page() {
  return <ShenzhiAiPage />;
}

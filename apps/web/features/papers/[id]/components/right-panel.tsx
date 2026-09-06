"use client";

import { useState } from "react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PaperAssistantPanel } from "./paper-assistant-panel";

export function PaperRightPanel({ paper }: { paper: KnowledgePaperDetail }) {
  const [tab, setTab] = useState("assistant");
  return (
    <aside className="flex h-[38rem] w-full shrink-0 flex-col border-t border-line bg-card lg:h-full lg:w-[360px] lg:border-t-0 lg:border-l xl:w-96">
      <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col">
        <TabsList aria-label="论文工具" className="shrink-0 border-b border-line px-3 py-3">
          <TabsTrigger value="assistant">Assistant</TabsTrigger>
          <TabsTrigger value="notes">My Notes</TabsTrigger>
          <TabsTrigger value="similar">Similar</TabsTrigger>
        </TabsList>
        {/* Keep the assistant mounted while switching tabs to preserve its session/stream. */}
        <div role="tabpanel" aria-label="Assistant" hidden={tab !== "assistant"} className={tab === "assistant" ? "min-h-0 flex-1" : "hidden"}>
          <PaperAssistantPanel paper={paper} />
        </div>
        {tab === "notes" && <div role="tabpanel" className="p-6 text-sm text-muted">笔记能力正在接入，暂不支持保存笔记。</div>}
        {tab === "similar" && <div role="tabpanel" className="p-6 text-sm text-muted">相似论文能力正在接入。</div>}
      </Tabs>
    </aside>
  );
}

"use client";

import { useState } from "react";
import { PanelRightClose } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PaperAssistantPanel } from "./paper-assistant-panel";

export function PaperRightPanel({
  paper,
  onCollapse,
  onMobileClose,
}: {
  paper: KnowledgePaperDetail;
  onCollapse: () => void;
  onMobileClose: () => void;
}) {
  const [tab, setTab] = useState("assistant");
  return (
    <aside className="paper-assistant-panel flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-line bg-card lg:h-full">
      <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col">
        <div className="flex w-full shrink-0 items-center gap-1 border-b border-line px-3 py-2">
          <TabsList aria-label="论文工具" className="flex min-w-0 flex-1 gap-1">
            <TabsTrigger value="assistant" className="min-w-0 flex-1 px-2">Assistant</TabsTrigger>
            <TabsTrigger value="notes" className="min-w-0 flex-1 px-2">My Notes</TabsTrigger>
            <TabsTrigger value="similar" className="min-w-0 flex-1 px-2">Similar</TabsTrigger>
          </TabsList>
          <button
            type="button"
            aria-label="收起 Assistant"
            title="收起 Assistant"
            className="hidden size-9 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-primary-soft hover:text-primary lg:inline-flex"
            onClick={onCollapse}
          >
            <PanelRightClose className="size-[18px]" />
          </button>
          <button type="button" aria-label="返回论文阅读" onClick={onMobileClose} className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-primary-soft lg:hidden"><PanelRightClose className="size-[18px]" /></button>
        </div>
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

"use client";

import { useState } from "react";
import { Layers, NotebookPen, PanelRightClose, type LucideIcon } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PaperAssistantPanel } from "./paper-assistant-panel";

const PANEL_TAB_CLASS =
  "relative min-w-0 flex-1 rounded-none px-2 py-0 after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:rounded-full after:bg-primary after:opacity-0 after:transition-opacity data-[state=active]:after:opacity-100";

function PanelEmptyState({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description: string }) {
  return (
    <div role="tabpanel" className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
        <Icon className="size-5" />
      </span>
      <div>
        <p className="text-sm font-medium text-ink">{title}</p>
        <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
      </div>
    </div>
  );
}

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
        <div className="flex h-12 w-full shrink-0 items-stretch gap-1 border-b border-line px-3">
          <TabsList aria-label="论文工具" className="flex min-w-0 flex-1 items-stretch gap-1">
            <TabsTrigger value="assistant" className={PANEL_TAB_CLASS}>Assistant</TabsTrigger>
            <TabsTrigger value="notes" className={PANEL_TAB_CLASS}>My Notes</TabsTrigger>
            <TabsTrigger value="similar" className={PANEL_TAB_CLASS}>Similar</TabsTrigger>
          </TabsList>
          <button
            type="button"
            aria-label="收起 Assistant"
            title="收起 Assistant"
            className="hidden size-9 shrink-0 self-center items-center justify-center rounded-lg text-muted transition-colors hover:bg-primary-soft hover:text-primary lg:inline-flex"
            onClick={onCollapse}
          >
            <PanelRightClose className="size-[18px]" />
          </button>
          <button type="button" aria-label="返回论文阅读" onClick={onMobileClose} className="inline-flex size-9 shrink-0 self-center items-center justify-center rounded-lg text-muted hover:bg-primary-soft lg:hidden"><PanelRightClose className="size-[18px]" /></button>
        </div>
        {/* Keep the assistant mounted while switching tabs to preserve its session/stream. */}
        <div role="tabpanel" aria-label="Assistant" hidden={tab !== "assistant"} className={tab === "assistant" ? "min-h-0 flex-1" : "hidden"}>
          <PaperAssistantPanel paper={paper} />
        </div>
        {tab === "notes" && (
          <PanelEmptyState icon={NotebookPen} title="笔记即将上线" description="笔记能力正在接入，暂不支持保存笔记。" />
        )}
        {tab === "similar" && (
          <PanelEmptyState icon={Layers} title="相似论文即将上线" description="相似论文能力正在接入。" />
        )}
      </Tabs>
    </aside>
  );
}

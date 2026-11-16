"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSearchDraft } from "@/hooks/use-search-draft";
import { useAuth } from "@/components/auth/auth-provider";
import { recordSearchSubmit } from "@/clients/backend/behavior";
import { ComposerShell } from "@/components/common/composer/composer";
import { useAgentLauncher } from "@/features/agent-chat/use-agent-launcher";
import type { ComposerEntryMode } from "@/types";
import type { ComposerSubmitPayload } from "@/types/ai-search";

const PLACEHOLDER_SEARCH = "请输入想检索的问题";
const PLACEHOLDER_AI = "用自然语言提问，例如 Diffusion Policy 有什么创新？";

/** 首页 Hero —— 简单搜索查论文库，智能搜索跳转问 AI */
export function SearchHero({
  initialQuery = "",
}: {
  initialQuery?: string;
}) {
  const router = useRouter();
  const { session } = useAuth();
  const draft = useSearchDraft("home-search", initialQuery, initialQuery);
  const [aiValue, setAiValue] = useState(initialQuery);
  const [chosenMode, setEntryMode] = useState<ComposerEntryMode | null>(null);
  const entryMode = chosenMode ?? (draft.value ? "search" : "ai");
  const value = entryMode === "search" ? draft.value : aiValue;
  const setValue = entryMode === "search" ? draft.set : setAiValue;
  const changeEntryMode = (next: ComposerEntryMode) => {
    if (next === entryMode) return;
    // Switching modes keeps the current input, as in the existing Composer.
    if (next === "search") draft.set(aiValue);
    else setAiValue(draft.value);
    setEntryMode(next);
  };
  const agent = useAgentLauncher();

  const send = async (payload: ComposerSubmitPayload) => {
    if (!payload.question.trim()) return;
    if (payload.entryMode === "search") {
      if (session?.user.id) recordSearchSubmit(payload.question, session.user.id);
      draft.clear();
      router.push(`/knowledge/search?q=${encodeURIComponent(payload.question)}`);
      return;
    }
    await agent.launch(payload.question);
  };

  return (
    <div className="w-full overflow-visible">
      <ComposerShell
        variant="home"
        value={value}
        onChange={setValue}
        onSend={send}
        placeholder={entryMode === "search" ? PLACEHOLDER_SEARCH : PLACEHOLDER_AI}
        entryMode={entryMode}
        onEntryModeChange={changeEntryMode}
        config={agent.config}
        model={agent.model}
        onModelChange={agent.setModel}
        replyMode={agent.mode}
        onReplyModeChange={agent.changeMode}
        attachments={agent.attachments}
        onAttachmentsChange={agent.setAttachments}
        skills={agent.skills}
        selectedSkills={agent.selectedSkills}
        onSelectSkill={agent.toggleSkill}
        onRemoveSkill={agent.toggleSkill}
        webSearchSwitch={false}
        hideStyleRow
        busy={agent.busy}
        disabled={!draft.ready}
      />
      {agent.error && <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{agent.error}</p>}
    </div>
  );
}

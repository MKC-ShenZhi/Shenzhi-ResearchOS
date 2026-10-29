"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSearchDraft } from "@/hooks/use-search-draft";
import { useAuth } from "@/components/auth/auth-provider";
import { recordSearchSubmit } from "@/clients/backend/behavior";
import { ComposerShell, type ComposerSkill } from "@/components/common/composer/composer";
import { createAgentSession, fetchAgentConfig, type AgentConfig, type AgentMode } from "@/clients/backend/agent";
import { saveAgentLaunch } from "@/features/agent-chat/launch-store";
import { notifyAgentSessionsChanged } from "@/features/agent-chat/session-events";
import type { ComposerEntryMode } from "@/types";
import type { ChatAttachment, ChatConfig, ComposerSubmitPayload } from "@/types/ai-search";

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
  const [agentConfig, setAgentConfig] = useState<AgentConfig>();
  const [model, setModel] = useState("default");
  const [mode, setMode] = useState<AgentMode>("fast");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<ComposerSkill[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchAgentConfig().then((config) => {
      setAgentConfig(config);
      setModel(config.default_model || "default");
    }).catch(() => setError("Agent 配置暂时不可用，请稍后重试"));
  }, []);

  const toggleSkill = (name: string) => {
    setSelectedSkills((current) => current.some((skill) => skill.name === name)
      ? current.filter((skill) => skill.name !== name)
      : [...current, ...(agentConfig?.skills.filter((skill) => skill.name === name) ?? [])]);
  };

  const send = async (payload: ComposerSubmitPayload) => {
    if (!payload.question.trim()) return;
    if (payload.entryMode === "search") {
      if (session?.user.id) recordSearchSubmit(payload.question, session.user.id);
      draft.clear();
      router.push(`/knowledge/search?q=${encodeURIComponent(payload.question)}`);
      return;
    }
    if (busy) return;
    setBusy(true);
    setError(null);
    const input = {
      prompt: payload.question.trim(),
      model: model === "default" ? undefined : model,
      mode,
      attachments,
      skills: selectedSkills.map((skill) => skill.name),
    };
    try {
      const session = await createAgentSession(input);
      const launchId = saveAgentLaunch(session.id, input);
      notifyAgentSessionsChanged();
      router.push(`/agents?session=${encodeURIComponent(session.id)}&launch=${encodeURIComponent(launchId)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法创建 Agent 会话，请稍后重试");
      setBusy(false);
    }
  };

  const config = {
    models: agentConfig?.models ?? [],
    default_model: agentConfig?.default_model ?? "default",
    modes: ["fast", "deep", "idea", "doubt"],
    quota: { used: 0, limit: 0, deep_used: 0, deep_limit: 0 },
    quota_enforced: false,
    // Do not fall back to the old Chat catalog while Agent config is loading. An empty limit
    // keeps upload/model choices unavailable until /agent/config is authoritative.
    upload: agentConfig?.upload ?? { max_size_mb: 0, max_files: 0, accept: [] },
  } as ChatConfig;

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
        config={config}
        model={model}
        onModelChange={setModel}
        replyMode={mode}
        onReplyModeChange={(next) => {
          if (next === "fast" || next === "deep" || next === "idea" || next === "doubt") setMode(next);
        }}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        skills={agentConfig?.skills ?? []}
        selectedSkills={selectedSkills}
        onSelectSkill={toggleSkill}
        onRemoveSkill={toggleSkill}
        webSearchSwitch={false}
        hideStyleRow
        busy={busy}
        disabled={!draft.ready}
      />
      {error && <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

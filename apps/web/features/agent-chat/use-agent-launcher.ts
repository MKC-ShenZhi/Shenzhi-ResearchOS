"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { ComposerSkill } from "@/components/common/composer/composer";
import { createAgentSession, fetchAgentConfig, type AgentConfig, type AgentMode } from "@/clients/backend/agent";
import type { ChatAttachment, ChatConfig, ChatReplyMode } from "@/types/ai-search";
import { saveAgentLaunch } from "./launch-store";
import { notifyAgentSessionsChanged } from "./session-events";

/**
 * 新对话入口（发现页智能搜索 / 深知 AI 页）共用的发起逻辑：
 * 读取 Agent 配置 → 创建持久化会话 → 一次性 launch 交给会话页执行首轮。
 */
export function useAgentLauncher() {
  const router = useRouter();
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

  const changeMode = (next: ChatReplyMode) => {
    if (next === "fast" || next === "deep" || next === "idea" || next === "doubt") setMode(next);
  };

  const launch = async (question: string) => {
    const prompt = question.trim();
    if (!prompt || busy) return;
    setBusy(true);
    setError(null);
    const input = {
      prompt,
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

  return {
    config, skills: agentConfig?.skills ?? [], model, setModel, mode, changeMode,
    attachments, setAttachments, selectedSkills, toggleSkill, busy, error, launch,
  };
}

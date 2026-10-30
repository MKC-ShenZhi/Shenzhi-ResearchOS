"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { ComposerShell } from "@/components/common/composer/composer";
import { AppShell } from "@/components/common/layout/app-shell";
import { useAgentLauncher } from "./use-agent-launcher";

/** 示例问题：点击只填入输入框，便于用户修改后再发送。 */
const EXAMPLE_PROMPTS = [
  "Diffusion Policy 有什么创新？",
  "梳理近两年多模态大模型幻觉缓解的主要方法",
  "对比 LoRA 与 QLoRA 在大模型微调中的优劣",
];

/** 深知 AI 新对话页 `/agents`：与发现页智能搜索同一条发起链路，发送后进入会话页。 */
export function AgentHomePage() {
  const agent = useAgentLauncher();
  const [input, setInput] = useState("");

  return (
    <AppShell>
      <div className="app-workspace-height flex min-h-0 flex-col items-center justify-center overflow-y-auto px-4 py-10 sm:px-6">
        <div className="w-full max-w-[860px]">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-agent text-white shadow-card" aria-hidden>
              <Sparkles className="size-6" strokeWidth={2} />
            </div>
            <h1 className="text-2xl font-semibold text-ink">深知 AI</h1>
            <p className="mt-2 text-sm text-muted">检索文献、梳理研究脉络、对比方法，或生成带引用的研究报告</p>
          </div>
          <ComposerShell
            value={input}
            onChange={setInput}
            onSend={(payload) => void agent.launch(payload.question)}
            placeholder="用自然语言提问，例如 Diffusion Policy 有什么创新？"
            modeSwitch={false}
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
          />
          {agent.error && <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{agent.error}</p>}
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {EXAMPLE_PROMPTS.map((prompt) => (
              <button key={prompt} type="button" disabled={agent.busy} onClick={() => setInput(prompt)}
                className="cursor-pointer rounded-full border border-line bg-card px-3 py-1.5 text-[13px] text-ink-2 transition-colors hover:border-primary/40 hover:text-primary disabled:cursor-default disabled:opacity-40">
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

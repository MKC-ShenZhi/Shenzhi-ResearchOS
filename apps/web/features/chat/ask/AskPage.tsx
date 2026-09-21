import { AgentChat } from "@/features/chat/components/agent-chat";
import type { ChatModelId, ChatReplyMode } from "@/types/ai-search";

/** 首页问 AI 兼容入口，与 /agents 共用 Chat Feature。 */
export function AskPage({
  question,
  initialMode,
  initialModel,
  initialWebSearch,
  initialSessionId,
  invalidSession,
}: {
  question: string;
  initialMode?: ChatReplyMode;
  initialModel?: ChatModelId;
  initialWebSearch?: boolean;
  initialSessionId?: string | null;
  invalidSession?: boolean;
}) {
  return (
    <>
      {/* `q` is a one-shot initial-question command from Search, not a
          session navigation mechanism; changing it must start a fresh turn. */}
      <AgentChat
        key={question}
        question={question}
        initialMode={initialMode}
        initialModel={initialModel}
        initialWebSearch={initialWebSearch}
        initialSessionId={initialSessionId}
        invalidSession={invalidSession}
      />
    </>
  );
}

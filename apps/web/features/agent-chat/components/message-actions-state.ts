import { isMarkdownBlock, type AgentMessage } from "../../../clients/backend/agent-message";

/** Copy the displayed answer only; never fall back to process/reasoning data. */
export function messageCopyText(message: AgentMessage | null, content: string): string {
  return message
    ? message.blocks.filter(isMarkdownBlock).map((block) => block.content).filter((text) => text.trim()).join("\n\n")
    : content;
}

export function canShowMessageActions(message: AgentMessage | null, status: string | undefined, isStreaming: boolean, text: string): boolean {
  return !isStreaming && status !== "running" && message?.status !== "running" && !!text.trim();
}

export type MessageFeedback = "like" | "dislike" | null;

export function toggleFeedback(current: MessageFeedback, next: Exclude<MessageFeedback, null>): MessageFeedback {
  return current === next ? null : next;
}

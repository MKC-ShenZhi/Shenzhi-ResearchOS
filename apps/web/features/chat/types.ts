import type {
  ChatAttachment,
  ChatCapabilities,
  ChatMessageStatus,
  ChatModelId,
  ChatReference,
  ChatReplyMode,
  KnowledgeGroundingState,
} from "../../types/ai-search";

export interface ChatTurn {
  localId: string;
  role: "user" | "assistant";
  content: string;
  reasoning: string;
  status: ChatMessageStatus;
  thought: string;
  references: ChatReference[];
  followups: string[];
  warnings: string[];
  readCount?: number;
  durationMs?: number;
  messageId?: string;
  lastEventId?: string;
  resumeFromStreaming?: boolean;
  error?: string;
  requestId?: string;
  knowledgeGrounding?: KnowledgeGroundingState;
}

export interface ChatSessionPreferences {
  mode: ChatReplyMode;
  model: ChatModelId;
  webSearch: boolean;
  entryMode: "search" | "ai";
}

export interface ChatSendInput {
  question: string;
  mode: ChatReplyMode;
  model: ChatModelId;
  web_search: boolean;
  attachments: ChatAttachment[];
  capabilities: ChatCapabilities;
}

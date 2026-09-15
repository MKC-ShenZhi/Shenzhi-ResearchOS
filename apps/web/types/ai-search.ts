/** 与 docs/dev/项目介绍.md 及 PRD 对齐的会话 / 流式契约 */

export type ChatSessionType = "research" | "chat";

export type ChatReplyMode = "fast" | "deep" | "idea" | "doubt";

export interface KnowledgeCapability {
  enabled: boolean;
}

export interface ChatCapabilities {
  knowledge: KnowledgeCapability;
}

/** 具体大模型 ID，如 deepseek-chat、gpt-4o */
export type ChatModelId = string;

export type ModelProvider =
  | "openai"
  | "anthropic"
  | "google"
  | "deepseek"
  | "zhipu"
  | "platform";

export type ChatAttachmentKind =
  | "file"
  | "paper"
  | "patent"
  | "funding"
  | "scholar"
  | "institution"
  | "session"
  | "project";

export interface ChatAttachment {
  kind: ChatAttachmentKind;
  file_id?: string;
  ref_id?: string;
  title?: string;
  warning?: string;
}

export interface CreateChatSessionRequest {
  type: ChatSessionType;
  question: string;
  mode: ChatReplyMode;
  model: ChatModelId;
  web_search: boolean;
  attachments: ChatAttachment[];
  capabilities: ChatCapabilities;
}

export interface SendChatMessageRequest {
  question: string;
  mode?: ChatReplyMode;
  model?: ChatModelId;
  web_search?: boolean;
  attachments?: ChatAttachment[];
  capabilities?: ChatCapabilities;
}

export interface CreateChatSessionResponse {
  session_id: string;
  message_id: string;
  last_event_id?: string;
}

export type ChatMessageStatus = "streaming" | "done" | "failed" | "stopped";

export type KnowledgeGroundingState = "grounded" | "unavailable" | "unverified";

export type ChatSourceType =
  | "paper"
  | "patent"
  | "funding"
  | "scholar"
  | "institution"
  | "web";

export interface ChatReference {
  /** Canonical Knowledge/Reference Snapshot fields. */
  referenceId: string;
  resourceType: ChatSourceType;
  resourceId: string;
  title: string;
  content: string;
  metadata: {
    authors?: string[];
    year?: number | null;
    venue?: string | null;
  };
  provenance?: unknown;
  score?: number | null;
  /** Legacy display aliases retained while old persisted sessions drain. */
  ordinal?: number;
  source_type?: ChatSourceType;
  source_id?: string;
  venue?: string | null;
  org?: string | null;
  authors?: string;
  citation_count?: number | null;
  recommended?: boolean;
  url?: string | null;
}

export interface StreamMetaEvent {
  read_count?: number;
  phase?: string;
  ephemeral?: boolean;
  arxiv_resolved?: number;
  context_truncated?: boolean;
  warnings?: string[];
  knowledge_grounding?: KnowledgeGroundingState;
}

export interface StreamDeltaEvent {
  text?: string;
  reasoning?: string;
}

export interface StreamRefsEvent {
  references: ChatReference[];
}

export interface StreamFollowupsEvent {
  items: string[];
}

export interface StreamDoneEvent {
  duration_ms: number;
  status: ChatMessageStatus;
  knowledge_grounding?: KnowledgeGroundingState;
}

export interface StreamErrorEvent {
  code: number | string;
  message: string;
  category?: string;
  knowledge_code?: string;
}

export interface ChatModelOption {
  value: ChatModelId;
  /** 列表与 pill 上显示的模型名 */
  label: string;
  provider: ModelProvider;
  enabled: boolean;
  reason?: string;
  description?: string;
}

export interface ChatConfig {
  default_model?: string;
  quota_enforced?: boolean;
  models: ChatModelOption[];
  modes: ChatReplyMode[];
  quota: {
    used: number;
    limit: number;
    deep_used: number;
    deep_limit: number;
  };
  upload: {
    max_size_mb: number;
    max_files: number;
    accept: string[];
  };
}

export interface ApiEnvelope<T> {
  code: number;
  data?: T;
  message?: string;
}

/** Composer payload；Chat adapter 会补充 capabilities。 */
export interface ComposerSubmitPayload {
  entryMode: "search" | "ai";
  /** Chat-only capability toggle; independent from the page entry mode. */
  knowledgeEnabled?: boolean;
  question: string;
  mode: ChatReplyMode;
  model: ChatModelId;
  web_search: boolean;
  attachments: ChatAttachment[];
}

/** Backend protocol types shared by Chat and the search/home composer. */
export interface ChatSessionSummary {
  id: string;
  title: string;
  favorite: boolean;
  updated_at: number;
  mode: ChatReplyMode;
  model: ChatModelId;
  web_search: boolean;
  capabilities?: ChatCapabilities;
}

export interface ChatStoredMessage {
  last_event_id: string;
  id: string;
  question: string;
  content: string;
  reasoning: string;
  status: ChatMessageStatus;
  references: ChatReference[];
  followups: string[];
  duration_ms: number;
  error: string | null;
  warnings: string[];
  knowledge_grounding?: KnowledgeGroundingState;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  messages: ChatStoredMessage[];
}

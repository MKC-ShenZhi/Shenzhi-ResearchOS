/** Compatibility entrypoint for shared Chat protocol types. */
export type { ApiEnvelope } from "../clients/backend/types";
export type {
  ChatAttachment,
  ChatAttachmentKind,
  ChatCapabilities,
  ChatConfig,
  ChatMessageStatus,
  ChatModelId,
  ChatModelOption,
  ChatReference,
  ChatReplyMode,
  ChatSessionDetail,
  ChatSessionSummary,
  ChatSessionType,
  ChatSourceType,
  ChatStoredMessage,
  CreateChatSessionRequest,
  CreateChatSessionResponse,
  KnowledgeCapability,
  KnowledgeGroundingState,
  ModelProvider,
  SendChatMessageRequest,
  StreamDeltaEvent,
  StreamDoneEvent,
  StreamErrorEvent,
  StreamFollowupsEvent,
  StreamMetaEvent,
  StreamRefsEvent,
} from "../clients/backend/chat/types";

import type { ChatAttachment, ChatModelId, ChatReplyMode } from "../clients/backend/chat/types";

/** Composer payload is a shared UI contract, not a Backend transport DTO. */
export interface ComposerSubmitPayload {
  entryMode: "search" | "ai";
  knowledgeEnabled?: boolean;
  question: string;
  mode: ChatReplyMode;
  model: ChatModelId;
  web_search: boolean;
  attachments: ChatAttachment[];
}

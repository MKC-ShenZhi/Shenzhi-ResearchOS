import type { ModelOption } from "../clients/backend/model-types";

export type { ApiEnvelope } from "../clients/backend/types";
export type { ModelOption, ModelProvider } from "../clients/backend/model-types";

/** Shared Composer contracts used by the Agent entry points. */
export type ReplyMode = "fast" | "deep" | "idea" | "doubt";
export type ModelId = string;

export type ComposerAttachmentKind = "file" | "paper" | "patent" | "funding" | "scholar" | "institution" | "session" | "project";
export interface ComposerAttachment {
  kind: ComposerAttachmentKind;
  file_id?: string;
  ref_id?: string;
  title?: string;
  warning?: string;
}

export interface ComposerConfig {
  default_model?: string | null;
  quota_enforced?: boolean;
  models: ModelOption[];
  modes: ReplyMode[];
  quota: { used: number; limit: number; deep_used: number; deep_limit: number };
  upload: { max_size_mb: number; max_files: number; accept: string[] };
}

/** Composer payload is a shared UI contract, not a Backend transport DTO. */
export interface ComposerSubmitPayload {
  entryMode: "search" | "ai";
  knowledgeEnabled?: boolean;
  question: string;
  mode: ReplyMode;
  model: ModelId;
  web_search: boolean;
  attachments: ComposerAttachment[];
}

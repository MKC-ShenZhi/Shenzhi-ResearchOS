import { fetchChatConfig } from "../../../clients/backend/chat";
import type {
  ChatConfig,
  ChatModelOption,
} from "../../../clients/backend/chat/types";
import { CHAT_MODEL_CATALOG } from "./model-catalog";

/** Availability, branding and capabilities belong to the backend Registry. */
export function mergeChatModelCatalog(backendModels: ChatModelOption[]): ChatModelOption[] {
  return backendModels.map((model) => ({ ...model }));
}

export const FALLBACK_CHAT_CONFIG: ChatConfig = {
  models: CHAT_MODEL_CATALOG.map((model) => ({ ...model, enabled: false })),
  quota_enforced: false,
  modes: ["fast", "deep", "idea", "doubt"],
  quota: { used: 0, limit: 20, deep_used: 0, deep_limit: 5 },
  upload: {
    max_size_mb: 20,
    max_files: 5,
    accept: [".pdf", ".md", ".markdown", ".txt"],
  },
};

export async function getChatConfig(): Promise<ChatConfig> {
  try {
    const config = await fetchChatConfig();
    return { ...config, models: mergeChatModelCatalog(config.models) };
  } catch {
    return FALLBACK_CHAT_CONFIG;
  }
}

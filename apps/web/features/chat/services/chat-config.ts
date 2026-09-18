import { fetchChatConfig } from "../../../clients/backend/chat";
import type {
  ChatConfig,
  ChatModelOption,
  ModelProvider,
} from "../../../types/ai-search";
import { CHAT_MODEL_CATALOG, chatModelLabel } from "./model-catalog";

const BACKEND_ONLY_LABELS: Record<
  string,
  Pick<ChatModelOption, "label" | "provider" | "description">
> = {
  "qwen-plus": { label: "通义 Plus", provider: "platform", description: "百炼默认对话模型" },
  "qwen-max": { label: "通义 Max", provider: "platform", description: "更强推理与长文本" },
  "qwen-turbo": { label: "通义 Turbo", provider: "platform", description: "低延迟快速回复" },
  "deepseek-v3": { label: "DeepSeek V3", provider: "deepseek", description: "百炼接入的对话模型" },
  "deepseek-r1": { label: "DeepSeek R1", provider: "deepseek", description: "百炼接入的推理模型" },
};

/** Merge the enabled Backend models with the full product catalog. */
export function mergeChatModelCatalog(backendModels: ChatModelOption[]): ChatModelOption[] {
  const enabledIds = new Set(backendModels.filter((model) => model.enabled).map((model) => model.value));
  const catalogIds = new Set(CHAT_MODEL_CATALOG.map((model) => model.value));
  const enabledBackendOnly = backendModels
    .filter((model) => model.enabled && !catalogIds.has(model.value))
    .map((model) => {
      const metadata = BACKEND_ONLY_LABELS[model.value];
      return {
        value: model.value,
        label: metadata?.label ?? model.label ?? chatModelLabel(model.value),
        provider: (metadata?.provider ?? model.provider ?? "platform") as ModelProvider,
        enabled: true,
        description: metadata?.description ?? model.description,
      } satisfies ChatModelOption;
    });

  const catalog = CHAT_MODEL_CATALOG.map((item) => ({
    ...item,
    enabled: enabledIds.has(item.value),
    reason: enabledIds.has(item.value) ? undefined : item.reason ?? "not_subscribed",
  }));
  return [...enabledBackendOnly, ...catalog];
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

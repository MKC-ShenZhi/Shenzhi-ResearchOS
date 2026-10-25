import type { ChatConfig, ChatModelId, ChatModelOption } from "../../../clients/backend/chat/types";

/** Display-only placeholders for a failed config request. Never imply availability. */
export const CHAT_MODEL_CATALOG: ChatModelOption[] = [
  { value: "qwen-plus", label: "通义 Plus", provider: "platform", enabled: false, reason: "config_unavailable" },
  { value: "deepseek-chat", label: "DeepSeek Chat", provider: "deepseek", enabled: false, reason: "config_unavailable" },
  { value: "glm-4-plus", label: "GLM-4 Plus", provider: "zhipu", enabled: false, reason: "config_unavailable" },
];

// The backend resolves this sentinel according to server configuration.
export const DEFAULT_CHAT_MODEL: ChatModelId = "default";
export const CHAT_MODEL_IDS = CHAT_MODEL_CATALOG.map((model) => model.value);

export function normalizeChatModelId(value?: string | null): ChatModelId {
  // Preserve registry IDs and historical IDs; only the server knows their aliases.
  return value?.trim() || DEFAULT_CHAT_MODEL;
}

export function chatModelLabel(value: ChatModelId): string {
  return CHAT_MODEL_CATALOG.find((model) => model.value === value)?.label ?? value;
}

export function modelUnavailableReason(reason?: string): string {
  switch (reason) {
    case "provider_not_configured": return "模型服务尚未配置";
    case "model_disabled": return "模型已禁用";
    case "unsupported_capability": return "模型不支持当前业务";
    case "config_unavailable": return "模型配置加载失败，请稍后重试";
    default: return "模型暂不可用";
  }
}

/** Resolve historical IDs using aliases published by the same backend Registry. */
export function selectAvailableModel(config: Pick<ChatConfig, "models" | "default_model">, preferred?: string): string {
  const selected = config.models.find((model) => model.enabled
    && (model.value === preferred || model.aliases?.includes(preferred ?? "")));
  return selected?.value ?? config.default_model ?? config.models.find((model) => model.enabled)?.value ?? preferred ?? "default";
}

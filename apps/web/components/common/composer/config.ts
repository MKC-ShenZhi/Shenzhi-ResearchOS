import type { ComposerConfig, ModelId, ModelOption } from "@/types/ai-search";

// The backend resolves this sentinel according to server configuration.
export const DEFAULT_MODEL: ModelId = "default";

/** Display-only placeholders for a failed config request. Never imply availability. */
const PLACEHOLDER_MODELS: ModelOption[] = [
  { value: "qwen-plus", label: "通义 Plus", provider: "platform", enabled: false, reason: "config_unavailable" },
  { value: "deepseek-chat", label: "DeepSeek Chat", provider: "deepseek", enabled: false, reason: "config_unavailable" },
  { value: "glm-4-plus", label: "GLM-4 Plus", provider: "zhipu", enabled: false, reason: "config_unavailable" },
];

export const FALLBACK_COMPOSER_CONFIG: ComposerConfig = {
  models: PLACEHOLDER_MODELS,
  quota_enforced: false,
  modes: ["fast", "deep", "idea", "doubt"],
  quota: { used: 0, limit: 20, deep_used: 0, deep_limit: 5 },
  upload: {
    max_size_mb: 20,
    max_files: 5,
    accept: [".pdf", ".md", ".markdown", ".txt"],
  },
};

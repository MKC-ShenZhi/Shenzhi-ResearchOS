import type { ChatModelId, ChatModelOption } from "../../../clients/backend/chat/types";

/** 前端可选的大模型目录（与 GET /chat/config 对齐） */
export const CHAT_MODEL_CATALOG: ChatModelOption[] = [
  {
    value: "qwen-plus",
    label: "通义 Plus",
    provider: "platform",
    enabled: true,
    description: "阿里百炼默认对话模型",
  },
  {
    value: "deepseek-reasoner",
    label: "DeepSeek R1",
    provider: "deepseek",
    enabled: true,
    description: "推理模型，适合复杂分析与证明",
  },
  {
    value: "gpt-4o",
    label: "GPT-4o",
    provider: "openai",
    enabled: false,
    reason: "not_subscribed",
    description: "OpenAI 旗舰多模态模型",
  },
  {
    value: "gpt-4o-mini",
    label: "GPT-4o mini",
    provider: "openai",
    enabled: false,
    reason: "not_subscribed",
    description: "OpenAI 轻量快速模型",
  },
  {
    value: "claude-3-5-sonnet",
    label: "Claude 3.5 Sonnet",
    provider: "anthropic",
    enabled: false,
    reason: "not_subscribed",
    description: "Anthropic 长上下文推理",
  },
  {
    value: "gemini-2-flash",
    label: "Gemini 2.0 Flash",
    provider: "google",
    enabled: false,
    reason: "not_subscribed",
    description: "Google 低延迟模型",
  },
  {
    value: "glm-4-plus",
    label: "GLM-4 Plus",
    provider: "zhipu",
    enabled: false,
    reason: "not_subscribed",
    description: "智谱 GLM，中文与代码表现好",
  },
];

export const DEFAULT_CHAT_MODEL: ChatModelId = "qwen-plus";

export const CHAT_MODEL_IDS = CHAT_MODEL_CATALOG.map((m) => m.value);

const LEGACY_MODEL_MAP: Record<string, ChatModelId> = {
  default: "deepseek-chat",
  subscription: "gpt-4o",
  byok: "gpt-4o-mini",
};

export function normalizeChatModelId(value?: string | null): ChatModelId {
  if (!value) return DEFAULT_CHAT_MODEL;
  if (CHAT_MODEL_IDS.includes(value)) return value;
  if (value in LEGACY_MODEL_MAP) return LEGACY_MODEL_MAP[value]!;
  return DEFAULT_CHAT_MODEL;
}

export function chatModelLabel(value: ChatModelId): string {
  return (
    CHAT_MODEL_CATALOG.find((m) => m.value === value)?.label ?? value
  );
}

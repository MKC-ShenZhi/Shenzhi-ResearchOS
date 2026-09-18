import { apiJson, apiPath } from "./http";
import { readSseStream, type SseEvent } from "./sse";
import { CHAT_MODEL_CATALOG, chatModelLabel } from "../../lib/data/chat-models";
import type {
  CreateChatSessionRequest, CreateChatSessionResponse, SendChatMessageRequest,
  StreamDeltaEvent, StreamDoneEvent, StreamErrorEvent, StreamFollowupsEvent,
  StreamMetaEvent, StreamRefsEvent, ChatSessionSummary, ChatSessionDetail, ChatConfig,
  ChatModelOption, ModelProvider,
} from "../../types/ai-search";

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

/** 后端 enabled 模型 + 完整产品目录（未开通项显示需订阅） */
export function mergeChatModelCatalog(backendModels: ChatModelOption[]): ChatModelOption[] {
  const enabledIds = new Set(
    backendModels.filter((m) => m.enabled).map((m) => m.value),
  );
  const catalogIds = new Set(CHAT_MODEL_CATALOG.map((m) => m.value));
  const enabledBackendOnly = backendModels
    .filter((m) => m.enabled && !catalogIds.has(m.value))
    .map((m) => {
      const meta = BACKEND_ONLY_LABELS[m.value];
      return {
        value: m.value,
        label: meta?.label ?? m.label ?? chatModelLabel(m.value),
        provider: (meta?.provider ?? m.provider ?? "platform") as ModelProvider,
        enabled: true,
        description: meta?.description ?? m.description,
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
    const data = await apiJson<ChatConfig>("/chat/config");
    return { ...data, models: mergeChatModelCatalog(data.models) };
  } catch {
    return FALLBACK_CHAT_CONFIG;
  }
}

export function createChatSession(
  body: CreateChatSessionRequest,
  init?: RequestInit,
) {
  return apiJson<CreateChatSessionResponse>("/chat/sessions", {
    method: "POST",
    body: JSON.stringify(body),
    ...init,
  });
}

export function sendChatMessage(
  sessionId: string,
  body: SendChatMessageRequest,
  init?: RequestInit,
) {
  return apiJson<CreateChatSessionResponse>(
    `/chat/sessions/${sessionId}/messages`,
    { method: "POST", body: JSON.stringify(body), ...init },
  );
}

export function stopChatMessage(messageId: string, init?: RequestInit) {
  return apiJson<{ ok: boolean }>(`/chat/messages/${messageId}/stop`, {
    method: "POST",
    ...init,
  });
}

export function resumeChatMessage(messageId: string, init?: RequestInit) {
  return apiJson<CreateChatSessionResponse>(
    `/chat/messages/${messageId}/resume`,
    { method: "POST", ...init },
  );
}

export interface ChatStreamHandlers {
  onRequestId?: (requestId: string | null) => void;
  onMeta?: (data: StreamMetaEvent) => void;
  onDelta?: (data: StreamDeltaEvent) => void;
  onRefs?: (data: StreamRefsEvent) => void;
  onFollowups?: (data: StreamFollowupsEvent) => void;
  onDone?: (data: StreamDoneEvent) => void;
  onError?: (data: StreamErrorEvent) => void;
}

function parseJson<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function streamChatMessage(
  messageId: string,
  handlers: ChatStreamHandlers,
  options: { signal?: AbortSignal; lastEventId?: string } = {},
) {
  let lastId = options.lastEventId;
  let terminal = false;

  const dispatch = (event: SseEvent) => {
    if (event.id) lastId = event.id;
    switch (event.event) {
      case "meta": {
        const data = parseJson<StreamMetaEvent>(event.data);
        if (data) handlers.onMeta?.(data);
        break;
      }
      case "delta": {
        const data = parseJson<StreamDeltaEvent>(event.data);
        if (data) handlers.onDelta?.(data);
        break;
      }
      case "refs": {
        const data = parseJson<StreamRefsEvent>(event.data);
        if (data?.references) handlers.onRefs?.(data);
        break;
      }
      case "followups": {
        const data = parseJson<StreamFollowupsEvent>(event.data);
        if (data?.items) handlers.onFollowups?.(data);
        break;
      }
      case "done": {
        terminal = true;
        const data = parseJson<StreamDoneEvent>(event.data) ?? {
          duration_ms: 0,
          status: "done",
        };
        handlers.onDone?.(data);
        break;
      }
      case "error": {
        terminal = true;
        const data = parseJson<StreamErrorEvent>(event.data) ?? {
          code: 20004,
          message: event.data,
        };
        handlers.onError?.(data);
        break;
      }
      default:
        break;
    }
  };

  await readSseStream(apiPath(`/chat/messages/${messageId}/stream`), {
    signal: options.signal,
    lastEventId: lastId,
    onRequestId: handlers.onRequestId,
    onEvent: dispatch,
  });

  if (!terminal && !options.signal?.aborted) throw new Error("连接提前结束，请继续生成");
  return lastId;
}


export function listChatSessions() {
  return apiJson<{ sessions: ChatSessionSummary[]; ephemeral: boolean }>("/chat/sessions");
}

export function getChatSession(id: string, init?: RequestInit) {
  return apiJson<ChatSessionDetail>(`/chat/sessions/${encodeURIComponent(id)}`, init);
}

export function updateChatSession(id: string, patch: { title?: string; favorite?: boolean }) {
  return apiJson<ChatSessionSummary>(`/chat/sessions/${encodeURIComponent(id)}`, {
    method: "PATCH", body: JSON.stringify(patch),
  });
}

export function deleteChatSession(id: string) {
  return apiJson<{ ok: boolean }>(`/chat/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
}

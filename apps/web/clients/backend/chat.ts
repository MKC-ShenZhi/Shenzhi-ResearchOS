import { apiJson, apiPath } from "./http";
import { readSseStream, type SseEvent } from "./sse";
import type {
  CreateChatSessionRequest, CreateChatSessionResponse, SendChatMessageRequest,
  StreamDeltaEvent, StreamDoneEvent, StreamErrorEvent, StreamFollowupsEvent,
  StreamMetaEvent, StreamRefsEvent, ChatSessionSummary, ChatSessionDetail, ChatConfig,
} from "../../types/ai-search";

export function fetchChatConfig(): Promise<ChatConfig> {
  return apiJson<ChatConfig>("/chat/config");
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

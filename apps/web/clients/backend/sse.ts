import { ApiError, requestHeaders } from "./http";

export interface SseEvent { id?: string; event: string; data: string }

/** Incremental SSE parser: UTF-8, CRLF, comments and multiline data. */
export async function readSseStream(
  url: string,
  options: {
    signal?: AbortSignal;
    lastEventId?: string;
    onEvent: (event: SseEvent) => void;
    onRequestId?: (requestId: string | null) => void;
  },
): Promise<void> {
  const headers = requestHeaders({ Accept: "text/event-stream" });
  if (options.lastEventId) headers.set("Last-Event-ID", options.lastEventId);
  const res = await fetch(url, { headers, signal: options.signal, cache: "no-store" });
  const requestId = res.headers.get("X-Request-ID");
  options.onRequestId?.(requestId);
  if (!res.ok || !res.body) throw new ApiError(20004, `SSE 连接失败 (${res.status})`, res.status, { requestId });
  if (!res.headers.get("content-type")?.includes("text/event-stream")) {
    throw new ApiError(20004, "生成服务未返回 SSE 数据", res.status, { requestId });
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let id: string | undefined;
  let event = "message";
  let data: string[] = [];
  const line = (raw: string) => {
    const value = raw.replace(/\r$/, "");
    if (!value) {
      if (data.length) options.onEvent({ id, event, data: data.join("\n") });
      id = undefined; event = "message"; data = [];
    } else if (value.startsWith("id:")) id = value.slice(3).trim();
    else if (value.startsWith("event:")) event = value.slice(6).trim();
    else if (value.startsWith("data:")) data.push(value.slice(5).replace(/^ /, ""));
  };
  try {
    while (true) {
      const chunk = await reader.read();
      buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true });
      let index: number;
      while ((index = buffer.indexOf("\n")) !== -1) {
        line(buffer.slice(0, index));
        buffer = buffer.slice(index + 1);
      }
      if (chunk.done) break;
    }
    if (buffer) line(buffer);
    line("");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

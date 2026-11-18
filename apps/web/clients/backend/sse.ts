import { ApiError, requestHeaders } from "./http";

export interface SseEvent { id?: string; event: string; data: string }

/** Incremental SSE parser: UTF-8, CRLF, comments and multiline data. */
export async function readSseStream(
  url: string,
  options: {
    body?: unknown;
    headers?: HeadersInit;
    signal?: AbortSignal;
    lastEventId?: string;
    idleTimeoutMs?: number;
    onEvent: (event: SseEvent) => void;
    onRequestId?: (requestId: string | null) => void;
  },
): Promise<void> {
  const connection = new AbortController();
  const abort = () => connection.abort(options.signal?.reason);
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) abort();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  const resetTimer = () => {
    clearTimeout(timer);
    if (options.idleTimeoutMs) timer = setTimeout(() => {
      timedOut = true;
      connection.abort();
    }, options.idleTimeoutMs);
  };
  resetTimer();
  try {
    const headers = requestHeaders(options.headers);
    headers.set("Accept", "text/event-stream");
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (options.lastEventId) headers.set("Last-Event-ID", options.lastEventId);
    const res = await fetch(url, {
      method: options.body === undefined ? "GET" : "POST",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: connection.signal,
      cache: "no-store",
    });
    resetTimer();
    const requestId = res.headers.get("X-Request-ID");
    options.onRequestId?.(requestId);
    if (!res.ok) {
      const error = await res.json().catch(() => null);
      throw new ApiError(error?.code ?? 20004, error?.message || `SSE 连接失败 (${res.status})`, res.status, { requestId });
    }
    if (!res.body) throw new ApiError(20004, "SSE 连接没有返回数据流", res.status, { requestId });
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
        resetTimer();
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
  } catch (error) {
    if (timedOut) throw new ApiError(20004, "连接长时间未收到数据，请重新连接或刷新结果", 504);
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

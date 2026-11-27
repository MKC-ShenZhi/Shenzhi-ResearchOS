import type { ModelOption } from "./model-types";
import { agentApiJson, agentApiPath } from "./http";
import { readSseStream, type SseEvent } from "./sse";
import { parseAgentMessage, parseAgentMessageEvent, type AgentMessage, type AgentMessageEvent } from "./agent-message";
export type { AgentMessage, AgentMessageEvent, ContentBlock, MarkdownBlock, Reference } from "./agent-message";

/**
 * Agent 基座（ShenzhiAi）客户端：产品路径使用 Backend Session；无状态 run 仅保留兼容。
 * 消息与事件协议见 docs/agent/message-blocks.md。
 */

export interface AgentSource { title?: string; url?: string; [key: string]: unknown }

/** agent 反问时的问题制品（与后端 ask_user 工具配套，见 agent/ask_user.py）。 */
export interface AgentQuestionOption {
  value: string;
  label?: string;
  description?: string | null;
}

/** 一次一个问题：点选项即作为回答发送，没有"部分确认"的中间状态。 */
export interface AgentQuestion {
  kind: 'question';
  question: string;
  options: AgentQuestionOption[];
  allow_other?: boolean;
  header?: string | null;
}

export interface AgentRunResult {
  /** awaiting_input = 本轮以提问结束，等用户回答后作为下一条消息继续。 */
  status: "done" | "stopped" | "failed" | "timeout" | "awaiting_input";
  /** 终态原始原因（stop/cancelled/timeout/max_turns/error…）：界面据此区分"到点了"与"你停的"。 */
  stop_reason?: string;
  final_text: string;
  message?: AgentMessage | null;
  output?: { kind?: string; report?: string; sources?: AgentSource[] } | null;
  /** 等待回答时的问题（后端已提到顶层，无需解析 output 判别联合）。 */
  question?: AgentQuestion | null;
  turns: number;
  duration_ms: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  truncated?: boolean;
  error?: { code: number; message: string } | null;
}

export interface AgentActivity {
  cancelled?: boolean;
  toolCallId: string;
  name: string;
  arguments: string;
  done: boolean;
  isError: boolean;
  durationMs: number;
  summary?: string;
}

export interface AgentSkillInfo { name: string; description: string }

export interface AgentConfig {
  models: ModelOption[];
  default_model: string | null;
  skills: AgentSkillInfo[];
  upload: { max_size_mb: number; max_files: number; accept: string[] };
}

export type AgentMode = "fast" | "deep" | "idea" | "doubt";

export interface AgentSessionSummary {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  settings: {
    model?: string | null;
    mode?: AgentMode;
    attachments?: unknown[];
    skills?: string[];
    workspace_id?: string | null;
  };
  branched_from?: string | null;
}

export interface AgentStoredTurn {
  id: string;
  user_content: string;
  assistant_content: string;
  message?: AgentMessage | null;
  reasoning: string;
  process: Array<
    { kind: "reasoning" | "text"; text: string } |
    { kind: "tool"; tool: AgentActivity }
  >;
  steers: Array<{ text: string; kind: "steer" | "follow_up" | "system" }>;
  report?: string | null;
  sources: AgentSource[];
  question?: AgentQuestion | null;
  warnings: string[];
  error?: string | null;
  stopped: boolean;
  stop_reason?: string | null;
  status: AgentRunResult["status"] | "running";
  settings: AgentSessionSummary["settings"];
  usage: Record<string, number | boolean>;
  created_at: number;
  completed_at?: number | null;
}

export interface AgentSessionDetail extends AgentSessionSummary {
  turns: AgentStoredTurn[];
}

export interface AgentSessionPage {
  sessions: AgentSessionSummary[];
  next_cursor: string | null;
  has_more: boolean;
  ephemeral: boolean;
}

export interface AgentRunInput {
  prompt: string;
  model?: string;
  mode: AgentMode;
  attachments: unknown[];
  skills: string[];
  workspace_id?: string;
}

export function fetchAgentConfig() {
  return agentApiJson<AgentConfig>("/agent/config");
}

export function steerAgentRun(runId: string, text: string) {
  return agentApiJson<{ injected: boolean }>(
    `/agent/run/${encodeURIComponent(runId)}/steer`,
    { method: "POST", body: JSON.stringify({ text }) });
}

export function stopAgentRun(runId: string) {
  return agentApiJson<{ stopping: boolean }>(
    `/agent/run/${encodeURIComponent(runId)}/stop`, { method: "POST" });
}

export function createAgentSession(input: AgentRunInput) {
  return agentApiJson<AgentSessionSummary>("/agent/sessions", {
    method: "POST", body: JSON.stringify(input),
  });
}

export function listAgentSessions(limit = 10, cursor?: string | null) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return agentApiJson<AgentSessionPage>(`/agent/sessions?${query.toString()}`);
}

export async function getAgentSession(sessionId: string) {
  const session = await agentApiJson<AgentSessionDetail>(`/agent/sessions/${encodeURIComponent(sessionId)}`);
  return { ...session, turns: session.turns.map((turn) => turn.message == null ? turn
    : { ...turn, message: parseAgentMessage(turn.message, turn.status) }) };

}

export function renameAgentSession(sessionId: string, title: string) {
  return agentApiJson<AgentSessionSummary>(`/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH", body: JSON.stringify({ title }),
  });
}

export function deleteAgentSession(sessionId: string) {
  return agentApiJson<{ ok: boolean }>(`/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function importLegacyAgentSession(body: {
  import_key: string; title: string; created_at?: number; updated_at?: number;
  branched_from?: string; turns: Array<Record<string, unknown>>;
}) {
  return agentApiJson<AgentSessionSummary>("/agent/sessions/import", {
    method: "POST", body: JSON.stringify(body),
  });
}

/** 会话导出（pi session-export）：POST 本地会话数据，返回 HTML 报告或 JSONL 文本。 */
export async function exportAgentSession(
  body: { title: string; messages: Array<Record<string, unknown>>; format: "html" | "jsonl" },
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(agentApiPath("/agent/session/export"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`导出失败 (${res.status})`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const utf8Name = /filename\*=UTF-8''([^;]+)/.exec(disposition);
  const plainName = /filename="?([^";]+)"?/.exec(disposition);
  return {
    blob: await res.blob(),
    filename: utf8Name ? decodeURIComponent(utf8Name[1]) : plainName ? plainName[1] : "session.html",
  };
}

export function createWorkspace() {
  return agentApiJson<{ workspace_id: string }>("/agent/workspace", { method: "POST" });
}

export interface WorkspaceUploadResult { path: string; size: number }

export function uploadWorkspaceFile(workspaceId: string, file: File, relativePath: string) {
  const body = new FormData();
  body.append("file", file);
  body.append("path", relativePath);
  return agentApiJson<WorkspaceUploadResult>(
    `/agent/workspace/${encodeURIComponent(workspaceId)}/files`, { method: "POST", body });
}

export async function streamAgentRun(
  body: { prompt: string; history?: Array<Record<string, unknown>>; model?: string;
          mode?: "fast" | "deep" | "idea" | "doubt";
          attachments?: unknown[]; workspace_id?: string; skills?: string[];
          session_id?: string },
  handlers: {
    onDelta: (text: string, reasoning: string, turn: number) => void;
    onMeta: (data: { warnings?: string[] }) => void;
    onToolCall: (activity: AgentActivity, turn: number) => void;
    onToolEnd: (toolCallId: string, isError: boolean, durationMs: number, summary: string, cancelled?: boolean) => void;
    onRunStart?: (runId: string) => void;
    onMessage?: (text: string, kind: "steer" | "follow_up" | "system") => void;
    onCompaction?: (data: { before_chars: number; after_chars: number }) => void;
    onMessageEvent?: (event: AgentMessageEvent) => void;
    onResult: (result: AgentRunResult) => void;
  },
  signal?: AbortSignal,
  idempotencyKey?: string,
): Promise<void> {
  await streamAgentEndpoint(agentApiPath("/agent/run"), body, handlers, signal,
    { "Idempotency-Key": idempotencyKey ?? crypto.randomUUID() });
}

export async function streamAgentSessionRun(
  sessionId: string,
  body: AgentRunInput,
  handlers: Parameters<typeof streamAgentRun>[1],
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<void> {
  await streamAgentEndpoint(
    agentApiPath(`/agent/sessions/${encodeURIComponent(sessionId)}/run`), body, handlers, signal,
    { "Idempotency-Key": idempotencyKey },
  );
}

export async function attachAgentSessionRun(
  sessionId: string,
  handlers: Parameters<typeof streamAgentRun>[1],
  signal?: AbortSignal,
): Promise<void> {
  await streamAgentEndpoint(
    agentApiPath(`/agent/sessions/${encodeURIComponent(sessionId)}/run/stream?after=0`),
    undefined, handlers, signal,
  );
}

async function streamAgentEndpoint(
  url: string,
  body: unknown,
  handlers: Parameters<typeof streamAgentRun>[1],
  signal?: AbortSignal,
  headers?: HeadersInit,
): Promise<void> {
  let completed = false;
  await readSseStream(url, {
    body,
    headers,
    signal,
    idleTimeoutMs: 45_000,
    onEvent: (event) => {
      dispatchAgentEvent(event, handlers);
      if (event.event === "result") completed = true;
    },
  });
  if (!completed) throw new Error("连接已中断，尚未收到最终结果。任务可能仍在执行，请重新连接或刷新结果。");
}

function dispatchAgentEvent(event: SseEvent, handlers: Parameters<typeof streamAgentRun>[1]): void {
  const messageEvent = parseAgentMessageEvent(event);
  if (messageEvent !== null) {
    handlers.onMessageEvent?.(messageEvent);
    return;
  }
  const data = JSON.parse(event.data);
  switch (event.event) {
    case "run_start":
      handlers.onRunStart?.(data.run_id);
      break;
    case "delta":
      handlers.onDelta(data.text ?? "", data.reasoning ?? "", data.turn ?? 0);
      break;
    case "meta":
      handlers.onMeta(data);
      break;
    case "message":
      handlers.onMessage?.(data.text ?? "",
        data.kind === "follow_up" || data.kind === "system" ? data.kind : "steer");
      break;
    case "compaction":
      handlers.onCompaction?.(data);
      break;
    case "tool_call":
      handlers.onToolCall({
        toolCallId: data.tool_call_id, name: data.name, arguments: data.arguments,
        done: false, isError: false, durationMs: 0,
      }, data.turn ?? 0);
      break;
    case "tool_end":
      handlers.onToolEnd(data.tool_call_id, Boolean(data.is_error), data.duration_ms ?? 0, data.summary ?? "", Boolean(data.cancelled));
      break;
    case "result":
      if (data.message != null) data.message = parseAgentMessage(data.message, data.status);
      handlers.onResult(data as AgentRunResult);
      break;
    default:
      break; // turn_start / turn_end / tools_enabled 前端无需处理
  }
}

"use client";

// ShenzhiAi 会话存储：浏览器本地持久化（pi 的本地会话文件在 Web 的对等物）。
// 会话 = 标题（首条提问自动生成）+ 完整轮次（含工具活动与产物）。

import type { AgentQuestion } from "@/clients/backend/agent";

/** 一次工具调用的持久化形态（页面侧 Activity 的存储对等物）。 */
export interface StoredActivity {
  toolCallId: string; name: string; arguments: string;
  done: boolean; isError: boolean; durationMs: number;
}

export interface StoredTurn {
  role: "user" | "assistant";
  content: string;
  reasoning?: string;
  /**
   * 旧字段：早期版本把工具调用单独存在这里。现在不再写入（工具已在 process 里，
   * 两份等于把参数存两遍），仅保留读取兼容——老会话靠它重建时间线。
   */
  activity?: StoredActivity[];
  /** 过程时间线（思考片段与工具交错）。旧会话没有该字段，读取时由 activity 兜底补齐。 */
  process?: Array<{ kind: "reasoning"; text: string } | { kind: "tool"; tool: StoredActivity }>;
  /** 旧字段：工具轮之间的过渡叙述。新写入仍保留，读取时并进相邻思考片段。 */
  narrations?: string[];
  /** 运行中的插话（steer）、系统提示（system）与旧格式的排队追问（follow_up），按发生顺序 */
  steers?: Array<{ text: string; kind: "steer" | "follow_up" | "system" }>;
  report?: string;
  sources?: Array<{ title?: string; url?: string }>;
  /** agent 反问的问题（status=awaiting_input）：持久化后历史会话仍能渲染选项 */
  question?: AgentQuestion;
  warnings?: string[];
  error?: string;
  stopped?: boolean;
  /** 终止原因（timeout / cancelled / max_turns …）：历史会话重开后仍能说明"为什么停"。 */
  stopReason?: string;
}

export interface AgentUsage { prompt: number; completion: number; runs: number }

export interface AgentSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: StoredTurn[];
  usage?: AgentUsage;
  branchedFrom?: string;
}

const KEY = "shenzhi-agent-sessions";
const MAX_SESSIONS = 50;

function load(): AgentSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as AgentSession[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persist(sessions: AgentSession[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(sessions.slice(0, MAX_SESSIONS)));
  } catch {
    // 存储已满/不可用：会话退化为仅当前页面内存，不影响对话
  }
}

export function listSessions(): AgentSession[] {
  return load().sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getSession(id: string): AgentSession | undefined {
  return load().find((session) => session.id === id);
}

export function saveSession(id: string, title: string, turns: StoredTurn[],
                            usageDelta?: { promptTokens: number; completionTokens: number }): AgentSession {
  const sessions = load();
  const now = Date.now();
  const existing = sessions.find((session) => session.id === id);
  const usage = existing?.usage ?? { prompt: 0, completion: 0, runs: 0 };
  if (usageDelta) {
    usage.prompt += usageDelta.promptTokens;
    usage.completion += usageDelta.completionTokens;
    usage.runs += 1;
  }
  const session: AgentSession = {
    id,
    title: title || existing?.title || "新会话",
    createdAt: existing?.createdAt ?? now,
    updatedAt: now,
    turns,
    usage,
    branchedFrom: existing?.branchedFrom,
  };
  persist([session, ...sessions.filter((item) => item.id !== id)]);
  return session;
}

/** pi 式分叉：以某会话为底复制出新会话（原会话保留）。 */
export function forkSession(id: string): AgentSession | undefined {
  const source = getSession(id);
  if (!source) return undefined;
  const now = Date.now();
  const fork: AgentSession = {
    id: newSessionId(),
    title: `${source.title} · 分叉`,
    createdAt: now,
    updatedAt: now,
    turns: source.turns,
    usage: source.usage ? { ...source.usage } : undefined,
    branchedFrom: source.id,
  };
  persist([fork, ...load()]);
  return fork;
}

export function deleteSession(id: string) {
  persist(load().filter((session) => session.id !== id));
}

export function newSessionId(): string {
  return `ses_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

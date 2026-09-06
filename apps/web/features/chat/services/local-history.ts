"use client";

import type { ChatTurn } from "../types";
import type { ChatIdentityScope } from "./identity-scope";

/** 仅在后端 Chat 不可用、且未获得 session_id 时的浏览器降级缓存；见 docs/chat/README.md */
const STORAGE_KEY_PREFIX = "shenzhi.ask.local-sessions";
// The legacy unscoped key is intentionally not migrated: its owner cannot be
// established safely, so assigning it to any identity could reintroduce a leak.
const MAX_SESSIONS = 30;
const TTL_MS = 24 * 60 * 60 * 1000;

export interface LocalAskSession {
  id: string;
  title: string;
  updatedAt: number;
  turns: ChatTurn[];
  mode: string;
  model: string;
  web_search: boolean;
  knowledge_enabled?: boolean;
}

function storageKey(scope: ChatIdentityScope): string {
  return `${STORAGE_KEY_PREFIX}:${scope}`;
}

function readAll(scope: ChatIdentityScope): LocalAskSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(storageKey(scope));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as LocalAskSession[];
    if (!Array.isArray(parsed)) return [];
    const now = Date.now();
    const live = parsed.filter((s) => now - s.updatedAt <= TTL_MS);
    if (live.length !== parsed.length) writeAll(scope, live);
    return live;
  } catch {
    return [];
  }
}

function writeAll(scope: ChatIdentityScope, sessions: LocalAskSession[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(storageKey(scope), JSON.stringify(sessions.slice(0, MAX_SESSIONS)));
}

export function listLocalAskSessions(scope: ChatIdentityScope): LocalAskSession[] {
  return readAll(scope).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getLocalAskSession(scope: ChatIdentityScope, id: string): LocalAskSession | null {
  return readAll(scope).find((s) => s.id === id) ?? null;
}

export function upsertLocalAskSession(scope: ChatIdentityScope, session: LocalAskSession) {
  const rest = readAll(scope).filter((s) => s.id !== session.id);
  writeAll(scope, [session, ...rest]);
}

export function deleteLocalAskSession(scope: ChatIdentityScope, id: string) {
  writeAll(scope, readAll(scope).filter((s) => s.id !== id));
}

export function titleFromQuestion(question: string): string {
  const q = question.trim() || "问 AI";
  return q.length > 24 ? `${q.slice(0, 24)}…` : q;
}

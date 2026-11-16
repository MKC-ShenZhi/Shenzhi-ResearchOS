"use client";

import type { AgentRunInput } from "@/clients/backend/agent";

const PREFIX = "shenzhi-agent-launch:";

export interface AgentLaunch extends AgentRunInput {
  sessionId: string;
  createdAt: number;
}

export function saveAgentLaunch(sessionId: string, input: AgentRunInput): string {
  const launchId = crypto.randomUUID();
  window.sessionStorage.setItem(`${PREFIX}${launchId}`, JSON.stringify({
    ...input, sessionId, createdAt: Date.now(),
  } satisfies AgentLaunch));
  return launchId;
}

/** One-shot handoff. Removing before run prevents React Strict Mode from launching twice. */
export function takeAgentLaunch(launchId: string, sessionId: string): AgentLaunch | null {
  const key = `${PREFIX}${launchId}`;
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  try {
    const launch = JSON.parse(raw) as AgentLaunch;
    if (launch.sessionId !== sessionId || Date.now() - launch.createdAt > 30 * 60_000) return null;
    window.sessionStorage.removeItem(key);
    return launch;
  } catch {
    return null;
  }
}

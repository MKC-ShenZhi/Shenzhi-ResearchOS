import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("session lifecycle uses one URL hydration path without visibility hacks", () => {
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");
  const workspace = readFileSync("features/chat/components/agent-chat.tsx", "utf8");
  const thread = readFileSync("features/chat/components/chat-thread.tsx", "utf8");
  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  const bridge = readFileSync("stores/ask-sidebar-bridge.ts", "utf8");

  assert.match(hook, /initialSessionId/);
  assert.match(hook, /readCurrentSessionId/);
  assert.match(hook, /readCurrentSessionId\(\) \?\? initialSessionId \?\? null/);
  assert.match(hook, /desiredSessionId/);
  assert.match(hook, /resolvedInitialSessionId/);
  assert.match(workspace, /useSearchParams/);
  assert.match(workspace, /desiredSessionId/);
  assert.match(hook, /onSessionIdChange/);
  assert.match(hook, /created\.session_id/);
  assert.match(hook, /void openSession\(urlSessionId\)/);
  assert.match(hook, /SessionGenerationGate/);
  assert.doesNotMatch(hook, /SessionHydrationGate|shouldResumeLastStream/);
  assert.match(hook, /STALE/);
  assert.match(hook, /isMissingSessionError/);
  assert.match(hook, /pendingAction\.targetPath/);
  assert.match(hook, /if \(resolvedInitialSessionId\)/);
  assert.match(hook, /setHydration\(true/);
  assert.match(hook, /setBusyValue\(false\)/);
  assert.match(hook, /onSessionIdChangeRef\.current\?\.\(null\)/);
  assert.match(hook, /handledUrlSessionId\.current = null/);
  assert.match(hook, /generation\.isCurrent\(\)/);
  assert.match(hook, /signal\.addEventListener\("abort"/);
  assert.match(hook, /queueMicrotask/);
  assert.equal((hook.match(/void openSession\(urlSessionId\)/g) ?? []).length, 1);
  assert.match(hook, /phaseForRestoredStatus/);
  assert.doesNotMatch(hook, /visibilitychange/);
  assert.doesNotMatch(workspace, /if \(isPending\) return <p/);
  assert.match(workspace, /authBootstrapComplete/);
  assert.match(workspace, /useState\(\(\) => !isPending\)/);
  assert.doesNotMatch(workspace, /authBootstrapListeners|useSyncExternalStore/);
  assert.match(workspace, /history\.replaceState/);
  assert.match(hook, /urlSessionId === sessionRef\.current/);
  assert.doesNotMatch(workspace, /getChatSession\(/);
  assert.match(sidebar, /listAgentSessions/);
  assert.match(sidebar, /`\/agents\?session=\$\{encodeURIComponent\(item\.id\)\}`/);
  assert.match(bridge, /activeSessionId/);
  assert.match(sidebar, /deleteAgentSession/);
  assert.match(sidebar, /renameAgentSession/);
  assert.doesNotMatch(sidebar, /requestLoad|removeHistoryItem|isMissingSessionError/);
  assert.doesNotMatch(sidebar, /requestNewChat/);
  assert.match(workspace, /该对话已过期或不存在/);
  assert.match(workspace, /新建对话/);
  assert.match(thread, /busy && turn\.status === "streaming"/);
});

test("Agent history click is URL-only and has no local-history branch", () => {
  const bridge = readFileSync("stores/ask-sidebar-bridge.ts", "utf8");
  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");

  assert.match(sidebar, /router\.push\(`\/agents\?session=\$\{encodeURIComponent\(item\.id\)\}`\)/);
  assert.doesNotMatch(sidebar, /item\.source|askSessionUrl|listLocalAskSessions/);
  assert.match(bridge, /targetPath\?: string/);
  assert.match(bridge, /requestReset/);
  assert.match(hook, /item\.source !== "local"/);
  assert.match(hook, /!urlSessionId && pendingLocalAction/);
});

test("stop cannot persist a stale local snapshot after a session switch", () => {
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");

  assert.match(
    hook,
    /if \(generation\.isCurrent\(\) && lastInput\.current && !sessionRef\.current\) \{[\s\S]*?persistLocalFallback/,
  );
  assert.doesNotMatch(hook, /revision\.current/);
});

test("delayed initial-question bootstrap cannot auto-send into a restored URL session", () => {
  const workspace = readFileSync("features/chat/components/agent-chat.tsx", "utf8");

  assert.match(
    workspace,
    /if \(!config \|\| resolvedInitialSessionId \|\| !question\.trim\(\) \|\| initialQuestionStarted\.current\) return;/,
  );
  assert.match(workspace, /initialQuestionStarted\.current/);
});

test("search q remains an explicit one-shot remount command", () => {
  const askPage = readFileSync("features/chat/ask/AskPage.tsx", "utf8");

  assert.match(askPage, /key=\{question\}/);
  assert.match(askPage, /one-shot initial-question command from Search/);
});

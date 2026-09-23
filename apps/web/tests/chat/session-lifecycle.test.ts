import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  SessionGenerationGate,
  phaseForRestoredStatus,
} from "../../features/chat/services/session-hydration";
import { transitionSessionNavigation } from "../../features/chat/services/session-navigation";
import { restoreTurns } from "../../features/chat/services/conversation";
import { useAskSidebarBridge } from "../../stores/ask-sidebar-bridge";

test("rapid A to B to A switching ignores every stale generation", () => {
  const gate = new SessionGenerationGate();
  const a1 = gate.begin("A");
  const b = gate.begin("B");
  const a2 = gate.begin("A");
  const writes: string[] = [];

  if (a1.isCurrent()) writes.push("A-old");
  if (b.isCurrent()) writes.push("B");
  if (a2.isCurrent()) writes.push("A-new");

  assert.deepEqual(writes, ["A-new"]);
  assert.equal(a1.controller.signal.aborted, true);
  assert.equal(b.controller.signal.aborted, true);
  assert.equal(a2.isCurrent(), true);
});

test("reset invalidates and aborts the active generation", () => {
  const gate = new SessionGenerationGate();
  const active = gate.begin("A");

  gate.cancel();

  assert.equal(active.isCurrent(), false);
  assert.equal(active.controller.signal.aborted, true);
  assert.equal(gate.current(), null);
});

test("old finish cannot release or rewrite a newer generation", () => {
  const gate = new SessionGenerationGate();
  const oldGeneration = gate.begin("A");
  const currentGeneration = gate.begin("B");

  const finished: string[] = [];
  const finish = (generation: typeof oldGeneration) => {
    if (generation.isCurrent() && generation.sessionId) finished.push(generation.sessionId);
  };
  finish(oldGeneration);
  finish(currentGeneration);

  assert.equal(oldGeneration.isCurrent(), false);
  assert.equal(currentGeneration.isCurrent(), true);
  assert.equal(gate.current()?.sessionId, "B");
  assert.deepEqual(finished, ["B"]);
});

test("only the current generation can complete", () => {
  const gate = new SessionGenerationGate();
  const oldGeneration = gate.begin("A");
  const currentGeneration = gate.begin("B");

  assert.equal(gate.complete(oldGeneration), false);
  assert.equal(gate.current(), currentGeneration);
  assert.equal(gate.complete(currentGeneration), true);
  assert.equal(gate.current(), null);
  assert.equal(currentGeneration.isCurrent(), false);
});

test("each first distinct history click requests one session hydration", () => {
  let state = { handledSessionId: "A" as string | null | undefined };
  const firstB = transitionSessionNavigation(state, "B");
  assert.equal(firstB.shouldHydrate, true);
  assert.equal(firstB.state.handledSessionId, "B");
  assert.equal(transitionSessionNavigation(firstB.state, "B").shouldHydrate, false);

  const hydrationRequests: string[] = [];

  for (const desiredSessionId of ["B", "C", "A"]) {
    const transition = transitionSessionNavigation(state, desiredSessionId);
    if (transition.shouldHydrate) hydrationRequests.push(desiredSessionId);
    state = transition.state;
  }

  assert.deepEqual(hydrationRequests, ["B", "C", "A"]);
  assert.equal(
    transitionSessionNavigation(state, "A").shouldHydrate,
    false,
  );

  const reset = transitionSessionNavigation(state, null);
  assert.equal(reset.shouldHydrate, true);
  assert.equal(reset.state.handledSessionId, null);
  assert.equal(transitionSessionNavigation(reset.state, null).shouldHydrate, false);
});

test("terminal and historical streaming restores never imply frontend busy", () => {
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");
  assert.doesNotMatch(hook, /shouldResumeLastStream/);
  assert.match(hook, /setBusyValue\(false\)/);
});

test("historical streaming restores as stopped so continuation is explicit", () => {
  const turns = restoreTurns({
    id: "session",
    title: "question",
    favorite: false,
    updated_at: 1,
    mode: "fast",
    model: "model",
    web_search: false,
    messages: [{
      id: "message",
      question: "question",
      content: "partial",
      reasoning: "",
      status: "streaming",
      references: [],
      followups: [],
      duration_ms: 1,
      error: null,
      warnings: [],
      last_event_id: "3",
    }],
  });

  assert.equal(turns[1]?.status, "stopped");
});

test("only a missing or expired session is classified as stale", () => {
  const errors = readFileSync("features/chat/services/errors.ts", "utf8");
  assert.match(errors, /export function isMissingSessionError/);
  assert.match(errors, /status === 404/);
});

test("restored terminal state is renderable without an active generation", () => {
  assert.deepEqual(
    [
      phaseForRestoredStatus("done"),
      phaseForRestoredStatus("failed"),
      phaseForRestoredStatus("stopped"),
      phaseForRestoredStatus("streaming"),
    ],
    ["READY", "FAILED", "STOPPED", "STOPPED"],
  );
});

test("active backend session identity is independently stored and clearable", () => {
  const store = useAskSidebarBridge;
  const { setActiveSessionId } = store.getState();

  assert.equal(typeof setActiveSessionId, "function");
  setActiveSessionId("session-a");
  assert.equal(store.getState().activeSessionId, "session-a");
  setActiveSessionId(null);
  assert.equal(store.getState().activeSessionId, null);
});

test("same-path session navigation subscribes to the query identity", () => {
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");
  const workspace = readFileSync("features/chat/components/agent-chat.tsx", "utf8");

  // The mounted workspace must receive the App Router's reactive query value;
  // reading window.location during render can lag Next's HistoryUpdater.
  assert.match(workspace, /useSearchParams/);
  assert.match(workspace, /desiredSessionId/);
  assert.match(hook, /desiredSessionId/);
  assert.doesNotMatch(hook, /searchParams\.toString\(\)/);
  assert.match(hook, /resolvedInitialSessionId/);
  assert.match(hook, /void openSession\(urlSessionId\)/);
});

test("explicit URL navigation remains the sole owner over bridge continuity", () => {
  const hook = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");
  const sidebar = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");

  assert.match(sidebar, /router\.push\(`\/agents\?session=\$\{encodeURIComponent\(item\.id\)\}`\)/);
  assert.match(hook, /readCurrentSessionId\(\) \?\? initialSessionId \?\? null/);
  assert.match(hook, /transitionSessionNavigation/);
  assert.match(hook, /void openSession\(urlSessionId\)/);
});

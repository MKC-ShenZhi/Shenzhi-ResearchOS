import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("Discover smart search creates a persistent Agent session and one-shot launch", () => {
  const source = readFileSync("features/search/components/search-hero.tsx", "utf8");
  assert.match(source, /components\/common\/composer\/composer/);
  assert.match(source, /fetchAgentConfig/);
  assert.match(source, /await createAgentSession\(input\)/);
  assert.match(source, /saveAgentLaunch\(session\.id, input\)/);
  assert.match(source, /model: model === "default" \? undefined : model/);
  assert.match(source, /mode,/);
  assert.match(source, /attachments,/);
  assert.match(source, /skills: selectedSkills\.map/);
  assert.match(source, /`\/agents\?session=/);
  assert.doesNotMatch(source, /getChatConfig|saveAskDraft|askQueryString|agents\/ask/);
});

test("simple search hides Agent-only controls without clearing their state", () => {
  const source = readFileSync("components/common/composer/composer.tsx", "utf8");
  assert.match(source, /isSmartSearch && selectedSkills/);
  assert.match(source, /isSmartSearch && attachments/);
  assert.match(source, /isSmartSearch && <>[\s\S]*?<PlusMenu/);
  assert.doesNotMatch(source, /setAttachments\(\[\]\)[\s\S]*setEntryMode/);
});

test("Agent conversation restores Backend turns and runs without browser-supplied history", () => {
  const source = readFileSync("features/agent-chat/shenzhi-ai-page.tsx", "utf8");
  assert.match(source, /getAgentSession\(sessionId\)/);
  assert.match(source, /session\.turns\.flatMap/);
  assert.match(source, /const runPrompt = useCallback/);
  assert.match(source, /streamAgentSessionRun\(sessionId, runInput/);
  assert.match(source, /takeAgentLaunch/);
  assert.match(source, /void runPrompt\(launch\)/);
  assert.doesNotMatch(source, /saveSession\(|listSessions\(|newSessionId\(/);
});

test("Sidebar uses cursor pagination and one shared scroll container", () => {
  const history = readFileSync("components/common/layout/sidebar-chat-history.tsx", "utf8");
  const sidebar = readFileSync("components/common/layout/app-sidebar.tsx", "utf8");
  assert.match(history, /const PAGE_SIZE = 10/);
  assert.match(history, /page\.next_cursor/);
  assert.match(history, /IntersectionObserver/);
  assert.match(history, /renameAgentSession/);
  assert.match(history, /deleteAgentSession/);
  assert.doesNotMatch(history, /overflow-y-auto|max-h-/);
  assert.doesNotMatch(sidebar, /HISTORY_NAV|历史\s*<\/p>/);
  assert.match(sidebar, /overflow-y-auto/);
});

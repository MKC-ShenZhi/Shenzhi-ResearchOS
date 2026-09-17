import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("grounding UI distinguishes grounded, degraded, and ordinary answers", () => {
  const panel = readFileSync("features/chat/components/thinking-status-panel.tsx", "utf8");
  const grid = readFileSync("features/chat/components/reference-grid.tsx", "utf8");
  const conversation = readFileSync("features/chat/services/conversation.ts", "utf8");

  assert.match(panel, /knowledgeGrounding/);
  assert.match(panel, /知识检索未生效/);
  assert.match(panel, /未形成可验证引用/);
  assert.match(grid, /knowledgeGrounding/);
  assert.match(grid, /检索资料/);
  assert.match(conversation, /knowledge_grounding/);
});

test("chat auxiliary panels stay collapsed until the user opens them", () => {
  const statusPanel = readFileSync("features/chat/components/thinking-status-panel.tsx", "utf8");
  const reasoningPanel = readFileSync("features/chat/components/reasoning-chain-panel.tsx", "utf8");

  assert.match(statusPanel, /const \[open, setOpen\] = useState\(false\)/);
  assert.match(reasoningPanel, /const \[open, setOpen\] = useState\(false\)/);
  assert.doesNotMatch(reasoningPanel, /setOpen\(true\)/);
  assert.match(statusPanel, /aria-expanded=\{open\}/);
  assert.match(reasoningPanel, /aria-expanded=\{open\}/);
});

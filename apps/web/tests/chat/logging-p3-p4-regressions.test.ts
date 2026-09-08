import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const HOOK = readFileSync("features/chat/hooks/use-chat-session.ts", "utf8");
const THREAD = readFileSync("features/chat/components/chat-thread.tsx", "utf8");
const COMPOSER = readFileSync("features/chat/components/composer.tsx", "utf8");

test("stop request is independent from the retired SSE abort signal", () => {
  assert.match(HOOK, /const streamingMessageId = \[\.\.\.turnsRef\.current\]/);
  assert.match(HOOK, /let messageId = currentMessageId\.current \?\? streamingMessageId/);
  assert.match(HOOK, /await stopChatMessage\(messageId\);/);
  assert.doesNotMatch(HOOK, /await stopChatMessage\(messageId, \{ signal: generation\.controller\.signal \}\);/);
});

test("completed turns expose the guarded resume path and retain an error bubble", () => {
  assert.match(HOOK, /\["done", "stopped", "failed"\]\.includes\(last\.status\)/);
  assert.match(THREAD, /\["done", "failed", "stopped"\]\.includes\(turn\.status\)/);
  assert.match(THREAD, /!failed && turn\.error/);
});

test("chat composer exposes a Knowledge toggle independent from entry mode", () => {
  assert.match(COMPOSER, /知识库/);
  assert.match(COMPOSER, /knowledgeEnabled/);
});

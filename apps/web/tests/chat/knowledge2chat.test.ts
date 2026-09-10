import assert from "node:assert/strict";
import test from "node:test";

import * as conversation from "../../features/chat/services/conversation";
import { isKnownCitation } from "../../features/chat/services/citation-validation";

test("Chat request adapter maps smart-search UI mode to nested Knowledge capability", () => {
  assert.equal(typeof conversation.capabilitiesForEntryMode, "function");
  assert.deepEqual(conversation.capabilitiesForEntryMode("ai"), {
    knowledge: { enabled: true },
  });
  assert.deepEqual(conversation.capabilitiesForEntryMode("search"), {
    knowledge: { enabled: false },
  });

  assert.deepEqual(conversation.chatInputFromComposer({
    entryMode: "ai",
    question: "q",
    mode: "fast",
    model: "m",
    web_search: false,
    attachments: [],
  }), {
    question: "q",
    mode: "fast",
    model: "m",
    web_search: false,
    attachments: [],
    capabilities: { knowledge: { enabled: true } },
  });

  assert.equal(conversation.chatInputFromComposer({
    entryMode: "search",
    question: "ordinary",
    mode: "fast",
    model: "m",
    web_search: false,
    attachments: [],
  }).capabilities.knowledge.enabled, false);

  assert.equal(conversation.chatInputFromComposer({
    entryMode: "ai",
    knowledgeEnabled: false,
    question: "ordinary chat without knowledge",
    mode: "fast",
    model: "m",
    web_search: false,
    attachments: [],
  }).capabilities.knowledge.enabled, false);
});

test("citation rendering keeps an unknown reference as ordinary text", () => {
  const known = new Set(["1"]);

  assert.equal(isKnownCitation("1", known), true);
  assert.equal(isKnownCitation("99", known), false);
});

test("restored degraded Knowledge turns do not infer a read count or citation state", () => {
  const turns = conversation.restoreTurns({
    id: "session",
    title: "question",
    favorite: false,
    updated_at: 1,
    mode: "fast",
    model: "model",
    web_search: false,
    capabilities: { knowledge: { enabled: true } },
    messages: [{
      last_event_id: "3",
      id: "message",
      question: "question",
      content: "ordinary fallback",
      reasoning: "",
      status: "done",
      references: [],
      followups: [],
      duration_ms: 1,
      error: null,
      warnings: ["knowledge unavailable"],
      knowledge_grounding: "unavailable",
    }],
  });

  assert.equal(turns[1]?.knowledgeGrounding, "unavailable");
  assert.equal(turns[1]?.readCount, undefined);
});

import assert from "node:assert/strict";
import { test } from "node:test";
import { FALLBACK_CHAT_CONFIG, getChatConfig, mergeChatModelCatalog } from "../../features/chat/services/chat-config";
import { modelUnavailableReason, normalizeChatModelId, selectAvailableModel } from "../../features/chat/services/model-catalog";
import { readFileSync } from "node:fs";

test("backend registry controls availability, provider identity and branding", () => {
  const models = [
    { value: "dashscope/deepseek-v3", label: "百炼 DeepSeek", provider: "deepseek", provider_id: "dashscope", enabled: true },
    { value: "zhipu/custom", label: "新 GLM", provider: "zhipu", enabled: true },
    { value: "new/disabled", label: "Disabled", provider: "new-brand", enabled: false, reason: "model_disabled" },
  ];
  assert.deepEqual(mergeChatModelCatalog(models), models);
  assert.equal(normalizeChatModelId("fourth/arbitrary"), "fourth/arbitrary");
  assert.equal(normalizeChatModelId("old-session-id"), "old-session-id");
  assert.equal(normalizeChatModelId(null), "default");
});

test("config failure keeps display placeholders disabled", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new Error("offline"); });
  const fallback = await getChatConfig();
  assert.deepEqual(fallback, FALLBACK_CHAT_CONFIG);
  assert.ok(fallback.models.every((model) => !model.enabled));
  assert.match(modelUnavailableReason("config_unavailable"), /加载失败/);
  assert.match(modelUnavailableReason("provider_not_configured"), /尚未配置/);
  assert.ok(!modelUnavailableReason("not_subscribed").includes("订阅"));
});

test("successful config does not add unavailable static products", async (t) => {
  const models = [{ value: "zhipu/private-version", label: "GLM", provider: "zhipu", enabled: true }];
  t.mock.method(globalThis, "fetch", async () => Response.json({ code: 0, data: { ...FALLBACK_CHAT_CONFIG, models } }));
  assert.deepEqual((await getChatConfig()).models, models);
});

test("historical session IDs use backend aliases before choosing a default", () => {
  const models = [
    { value: "dashscope/qwen-plus", label: "Qwen", provider: "platform", enabled: true },
    { value: "deepseek/deepseek-chat", label: "DeepSeek", provider: "deepseek", enabled: true, aliases: ["deepseek-chat"] },
  ];
  assert.equal(selectAvailableModel({ models, default_model: "dashscope/qwen-plus" }, "deepseek-chat"), "deepseek/deepseek-chat");
});

test("empty successful catalog with null default disables AI while retaining simple search", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({
    code: 0, data: { ...FALLBACK_CHAT_CONFIG, models: [], default_model: null },
  }));
  const config = await getChatConfig();
  assert.deepEqual(config.models, []);
  assert.equal(config.default_model, null);
  assert.equal(selectAvailableModel(config), "default");
  assert.equal(selectAvailableModel(config, "autodl/Kimi-K2.5"), "autodl/Kimi-K2.5");
  // Both legacy Chat and the current shared Composer must gate the button and
  // keyboard path only for AI, leaving simple search available.
  for (const path of ["features/chat/components/composer.tsx", "components/common/composer/composer.tsx"]) {
    const composer = readFileSync(path, "utf8");
    assert.match(composer, /const modelAvailable = config\.models\.some\(/);
    assert.match(composer, /const canSend =[\s\S]*?&& \(!isSmartSearch \|\| modelAvailable\)/);
    assert.match(composer, /\(intent \?\? entryMode\) === "ai" && !modelAvailable/);
    assert.match(composer, /disabled=\{!canSend\}/);
  }
  const picker = readFileSync("features/chat/components/composer-control-picker.tsx", "utf8");
  assert.match(picker, /current\?\.label \?\? "选择模型"/);
});

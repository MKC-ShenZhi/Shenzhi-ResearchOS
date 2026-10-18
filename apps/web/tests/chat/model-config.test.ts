import assert from "node:assert/strict";
import { test } from "node:test";
import { FALLBACK_CHAT_CONFIG, getChatConfig, mergeChatModelCatalog } from "../../features/chat/services/chat-config";
import { modelUnavailableReason, normalizeChatModelId, selectAvailableModel } from "../../features/chat/services/model-catalog";

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

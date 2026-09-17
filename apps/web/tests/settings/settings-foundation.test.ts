import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const tabs = readFileSync("features/settings/components/settings-tabs.tsx", "utf8");
const profile = readFileSync("features/settings/components/profile-panel.tsx", "utf8");
const notifications = readFileSync("features/settings/components/notifications-panel.tsx", "utf8");
const bff = readFileSync("app/api/v1/[...path]/route.ts", "utf8");
const profileEditor = readFileSync("features/settings/components/profile/profile-editor.tsx", "utf8");
const profileHook = readFileSync("features/settings/hooks/use-user-profile.ts", "utf8");
const profileClient = readFileSync("clients/profile/index.ts", "utf8");
const avatarOptions = readFileSync("features/settings/avatar-options.ts", "utf8");

test("settings keeps all deep links and falls back invalid values to profile", () => {
  for (const value of ["profile", "subscription", "usage", "agent", "mcp", "api", "notifications"]) {
    assert.match(readFileSync("features/settings/components/tab-config.tsx", "utf8"), new RegExp(`value: "${value}"`));
  }
  assert.match(tabs, /isSettingsTab\(requestedTab\)[\s\S]*requestedTab : "profile"/);
});

test("profile and notifications no longer expose fabricated biography or notification detail", () => {
  assert.doesNotMatch(profile, /NeurIPS|国家奖学金|清华大学人工智能研究院/);
  assert.doesNotMatch(notifications, /演示:|发表了新论文|本月用量/);
  assert.match(notifications, /通知投递渠道尚未启用/);
});

test("settings reuses the generic authenticated BFF", () => {
  assert.match(bff, /forwardToBusinessBackend/);
  assert.doesNotMatch(tabs, /x-shenzhi-user-id/i);
});

test("profile uses five local avatars and the authenticated profile API", () => {
  for (let index = 1; index <= 5; index += 1) {
    assert.match(avatarOptions, new RegExp(`avatar-0${index}\\.webp`));
  }
  assert.match(profileClient, /apiJson<UserProfile>\("\/profile"\)/);
  assert.match(profileClient, /method: "PATCH"/);
  assert.doesNotMatch(profileClient, /user_id/);
  assert.match(profileHook, /session\?\.user\.id/);
  assert.match(profileHook, /setProfile\(null\)/);
});

test("profile editor covers the stage two editable scholar fields", () => {
  for (const field of ["bio", "achievements", "educations", "biography", "institutions"]) {
    assert.match(profileEditor, new RegExp(`draft\\.${field}`));
  }
  assert.match(profileEditor, /moveItem/);
  assert.match(profileEditor, /保存失败，草稿已保留/);
  assert.doesNotMatch(profileEditor, /上传头像/);
});

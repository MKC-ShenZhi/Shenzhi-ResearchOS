import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const presets = readFileSync("lib/theme-presets.ts", "utf8");
const store = readFileSync("stores/theme.ts", "utf8");
const layout = readFileSync("app/layout.tsx", "utf8");
const styles = readFileSync("styles/globals.css", "utf8");
const settingsMenu = readFileSync("components/common/layout/settings-menu.tsx", "utf8");
const profilePanel = readFileSync("features/settings/components/profile-panel.tsx", "utf8");

const themeIds = [
  "shenzhi",
  "gpt",
  "claude",
  "alphaxiv",
  "apple-light",
  "apple-dark",
];

test("theme explorer exposes the existing theme plus five visual presets", () => {
  for (const id of themeIds) assert.match(presets, new RegExp(`id: "${id}"`));
  assert.match(settingsMenu, /THEME_PRESETS\.map/);
  assert.match(profilePanel, /THEME_PRESETS\.map/);
});

test("theme preset persists locally and applies before first paint", () => {
  assert.match(store, /shenzhi-theme-preset/);
  assert.match(store, /document\.documentElement\.dataset\.theme = preset/);
  assert.match(layout, /shenzhi-theme-preset/);
  assert.match(layout, /document\.documentElement\.dataset\.theme=p/);
  assert.match(store, /URLSearchParams\(window\.location\.search\)/);
});

test("every exploratory preset replaces the complete semantic color surface", () => {
  for (const id of themeIds.slice(1)) {
    assert.match(styles, new RegExp(`html\\[data-theme="${id}"\\]`));
  }
  for (const token of [
    "background",
    "sidebar",
    "card",
    "primary",
    "primary-soft",
    "agent",
    "ink",
    "ink-2",
    "muted",
    "faint",
    "chip",
    "panel",
    "line",
  ]) {
    assert.match(styles, new RegExp(`--color-${token}:`));
  }
});

test("only Apple dark forces dark component variants", () => {
  assert.match(store, /preset === "apple-dark"/);
  assert.match(store, /preset === "shenzhi"/);
  assert.doesNotMatch(store, /preset === "gpt"[^;]+classList/);
});

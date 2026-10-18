import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const presets = readFileSync("lib/theme-presets.ts", "utf8");
const store = readFileSync("stores/theme.ts", "utf8");
const layout = readFileSync("app/layout.tsx", "utf8");
const styles = readFileSync("styles/globals.css", "utf8");
const settingsMenu = readFileSync("components/common/layout/settings-menu.tsx", "utf8");
const profilePanel = readFileSync("features/settings/components/profile-panel.tsx", "utf8");
const customControls = readFileSync("components/common/custom-theme-controls.tsx", "utf8");
const customTheme = readFileSync("lib/custom-theme.ts", "utf8");

const themeIds = [
  "shenzhi",
  "gpt",
  "claude",
  "alphaxiv",
  "apple-light",
  "apple-dark",
  "apple-neo-purple",
  "apple-neo-lime",
  "apple-air-blue",
  "apple-air-violet",
  "spectrum-coral",
  "spectrum-amber",
  "spectrum-gold",
  "spectrum-emerald",
  "spectrum-cyan",
  "spectrum-cobalt",
  "spectrum-rose",
  "custom",
];

test("theme explorer exposes presets plus a custom palette", () => {
  for (const id of themeIds) assert.match(presets, new RegExp(`id: "${id}"`));
  assert.match(settingsMenu, /THEME_PRESETS\.map/);
  assert.match(profilePanel, /THEME_PRESETS\.map/);
  assert.match(settingsMenu, /CustomThemeControls/);
  assert.match(profilePanel, /CustomThemeControls/);
  assert.match(customControls, /type="color"/);
  assert.match(customControls, /CUSTOM_THEME_SWATCHES\.map/);
});

test("theme preset persists locally and applies before first paint", () => {
  assert.match(store, /shenzhi-theme-preset/);
  assert.match(store, /document\.documentElement\.dataset\.theme = preset/);
  assert.match(layout, /shenzhi-theme-preset/);
  assert.match(layout, /document\.documentElement\.dataset\.theme=p/);
  assert.match(store, /URLSearchParams\(window\.location\.search\)/);
  assert.match(customTheme, /shenzhi-theme-custom/);
  assert.match(layout, /shenzhi-theme-custom-vars/);
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
  assert.match(styles, /html:not\(\.dark\):not\(\[data-theme="shenzhi"\]\) :where\(\.bg-card\)/);
  assert.match(styles, /color-mix\(in srgb, var\(--color-card\)/);
});

test("only designated dark presets force dark component variants", () => {
  assert.match(store, /isDarkThemePreset\(preset\)/);
  assert.match(presets, /preset === "apple-dark"/);
  assert.match(presets, /preset === "apple-air-blue"/);
  assert.match(presets, /preset === "apple-air-violet"/);
  assert.match(presets, /preset === "spectrum-emerald"/);
  assert.match(presets, /preset === "spectrum-cobalt"/);
  assert.match(presets, /preset === "spectrum-rose"/);
  assert.match(store, /preset === "shenzhi"/);
  assert.match(store, /preset === "custom" && customTheme\.appearance === "dark"/);
  assert.doesNotMatch(store, /preset === "gpt"[^;]+classList/);
});

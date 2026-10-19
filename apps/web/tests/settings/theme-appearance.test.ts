import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";
import { createStore } from "zustand/vanilla";
import * as presets from "../../lib/theme-presets";
import * as customTheme from "../../lib/custom-theme";

type Mode = "light" | "dark" | "system";
type ThemeApi = {
  getState(): { mode: Mode; preset: presets.ThemePreset; setMode(mode: Mode): void; setPreset(preset: presets.ThemePreset): void };
};

function browser(preset: string, mode: Mode, systemDark: boolean) {
  const storage = new Map<string, string>([["shenzhi-theme-preset", preset], ["shenzhi-theme", mode]]);
  const properties = new Map<string, string>();
  const classes = new Set<string>();
  const root = {
    dataset: { theme: "shenzhi" },
    classList: { toggle: (name: string, active: boolean) => active ? classes.add(name) : classes.delete(name) },
    style: { setProperty: (key: string, value: string) => properties.set(key, value), removeProperty: (key: string) => properties.delete(key) },
  };
  let onSystemChange = () => {};
  const media = { matches: systemDark, addEventListener: (_name: string, callback: () => void) => { onSystemChange = callback; } };
  const context = {
    document: { documentElement: root },
    window: { location: { search: "" }, matchMedia: () => media },
    location: { search: "" },
    localStorage: { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value) },
    URLSearchParams,
  };
  return { context, root, classes, storage, properties, systemChange: (dark: boolean) => { media.matches = dark; onSystemChange(); } };
}

function firstPaint(browserState: ReturnType<typeof browser>) {
  const layout = readFileSync("app/layout.tsx", "utf8");
  const template = layout.match(/const themeScript = (`[^`]+`);/)?.[1];
  assert.ok(template);
  const script = runInNewContext(template, { ...presets, JSON });
  runInNewContext(script, browserState.context);
}

function loadStore(browserState: ReturnType<typeof browser>) {
  const source = ts.transpileModule(readFileSync("stores/theme.ts", "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports: { useThemeStore?: ThemeApi; hydrateThemeStoreFromStorage?: () => void } = {};
  runInNewContext(source, {
    ...browserState.context,
    exports,
    require: (id: string) => {
      if (id === "zustand") return { create: () => createStore };
      if (id === "@/lib/theme-presets") return presets;
      if (id === "@/lib/custom-theme") return customTheme;
      throw new Error(`Unexpected import: ${id}`);
    },
  });
  assert.ok(exports.useThemeStore);
  assert.ok(exports.hydrateThemeStoreFromStorage);
  return { store: exports.useThemeStore, hydrate: exports.hydrateThemeStoreFromStorage };
}

test("mode-aware presets agree at first paint, hydration, and system changes", () => {
  for (const preset of presets.MODE_THEME_PRESETS) {
    for (const mode of ["light", "dark", "system"] as const) {
      for (const systemDark of [false, true]) {
        const state = browser(preset, mode, systemDark);
        firstPaint(state);
        const expectedDark = mode === "dark" || (mode === "system" && systemDark);
        assert.equal(state.root.dataset.theme, preset);
        assert.equal(state.classes.has("dark"), expectedDark);
        const { store, hydrate } = loadStore(state);
        assert.equal(store.getState().preset, "shenzhi", "SSR defaults stay deterministic");
        hydrate();
        assert.equal(store.getState().preset, preset);
        assert.equal(state.classes.has("dark"), expectedDark);
        state.systemChange(!systemDark);
        assert.equal(state.classes.has("dark"), mode === "system" ? !systemDark : expectedDark);
        store.getState().setMode("dark");
        assert.equal(state.storage.get("shenzhi-theme"), "dark");
        assert.equal(state.root.dataset.theme, preset, "mode switch keeps preset");
        store.getState().setPreset("custom");
        assert.ok(state.properties.size > 0);
        store.getState().setPreset(preset);
        assert.equal(state.properties.size, 0, "custom inline tokens must not leak");
        firstPaint(state);
        hydrate();
        assert.equal(state.classes.has("dark"), true);
        assert.equal(state.root.dataset.theme, preset);
      }
    }
  }
});

test("existing fixed presets and custom appearance keep their behavior", () => {
  for (const { id } of presets.THEME_PRESETS) {
    if (presets.supportsThemeMode(id)) continue;
    const state = browser(id, "dark", true);
    const expectedDark = presets.isDarkThemePreset(id);
    firstPaint(state);
    assert.equal(state.classes.has("dark"), expectedDark, id);
    const { hydrate } = loadStore(state);
    hydrate();
    assert.equal(state.classes.has("dark"), expectedDark, id);
  }
  const state = browser("custom", "light", false);
  state.storage.set("shenzhi-theme-custom", JSON.stringify({ accent: "#315EFB", appearance: "dark" }));
  firstPaint(state);
  assert.ok(state.classes.has("dark"));
  loadStore(state).hydrate();
  assert.ok(state.classes.has("dark"));
});

const css = readFileSync("styles/globals.css", "utf8");
function tokens(selector: string) {
  const block = css.slice(css.indexOf(`${selector} {`)).split("}")[0];
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [match[1], match[2]]));
}
function luminance(hex: string) {
  const rgb = hex.slice(1).match(/../g)!.map((channel) => Number.parseInt(channel, 16) / 255);
  const linear = rgb.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}
function contrast(a: string, b: string) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test("black and white has neutral complete surfaces and AA reading/action contrast", () => {
  const light = tokens('html[data-theme="gpt"]');
  const dark = { ...light, ...tokens('html[data-theme="gpt"].dark') };
  for (const palette of [light, dark]) {
    for (const [key, value] of Object.entries(palette)) {
      if (!key.startsWith("--color-") || /danger|success/.test(key)) continue;
      assert.match(value, /^#[0-9a-f]{6}$/i, key);
      assert.equal(value.slice(1, 3), value.slice(3, 5), key);
      assert.equal(value.slice(3, 5), value.slice(5, 7), key);
    }
    for (const key of ["--page-wallpaper", "--surface-card-image", "--surface-panel-image", "--surface-sidebar-image", "--surface-chip-image"]) assert.equal(palette[key], "none");
    for (const surface of ["background", "card", "sidebar", "panel", "chip"]) {
      for (const text of ["ink", "ink-2", "muted", "faint"]) {
        assert.ok(contrast(palette[`--color-${text}`], palette[`--color-${surface}`]) >= 4.5, `${text} on ${surface}`);
      }
    }
    for (const action of ["primary", "primary-deep"]) assert.ok(contrast(palette["--color-primary-foreground"], palette[`--color-${action}`]) >= 4.5);
    assert.ok(contrast(palette["--color-primary"], palette["--color-primary-soft"]) >= 4.5);
  }
});

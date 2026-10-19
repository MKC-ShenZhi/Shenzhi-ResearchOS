import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import type { ReactNode } from "react";
import * as jsxRuntime from "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";
import Script from "next/script";
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

function renderLayout() {
  const source = ts.transpileModule(readFileSync("app/layout.tsx", "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const passthrough = ({ children }: { children: ReactNode }) => children;
  const dependencies: Record<string, unknown> = {
    "react/jsx-runtime": jsxRuntime,
    "next/script": { default: Script },
    "@/lib/theme-presets": presets,
    "@/styles/globals.css": {},
    "@/components/auth/auth-provider": { AuthProvider: passthrough },
    "@/components/common/feature-availability-provider": { FeatureAvailabilityProvider: passthrough },
    "@/components/common/theme-store-hydrator": { ThemeStoreHydrator: () => null },
    "@/providers/query-provider": { QueryProvider: passthrough },
  };
  const exports: { default?: (props: { children: ReactNode }) => ReactNode } = {};
  runInNewContext(source, {
    exports,
    require: (id: string) => {
      assert.ok(id in dependencies, `Unexpected layout import: ${id}`);
      return dependencies[id];
    },
  });
  assert.ok(exports.default);
  return renderToStaticMarkup(exports.default({ children: "page content" }));
}

const layoutHtml = renderLayout();

function firstPaint(browserState: ReturnType<typeof browser>) {
  const head = layoutHtml.match(/<head>([\s\S]*?)<\/head>/)?.[1];
  assert.ok(head, "theme initialization must be in the rendered head before body content");
  const script = head.match(/<script id="shenzhi-theme">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, "theme initialization must execute inline without waiting for Next.js runtime");
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

test("theme initializes before body content without the Next.js runtime", () => {
  const state = browser("custom", "system", false);
  const config = { accent: "#315EFB", appearance: "dark" } as const;
  const variables = customTheme.createCustomThemeVariables(config);
  state.storage.set(customTheme.CUSTOM_THEME_STORAGE_KEY, JSON.stringify(config));
  state.storage.set(customTheme.CUSTOM_THEME_VARS_STORAGE_KEY, JSON.stringify(variables));
  firstPaint(state);
  assert.equal(state.root.dataset.theme, "custom");
  assert.ok(state.classes.has("dark"));
  assert.deepEqual(Object.fromEntries(state.properties), variables);
});

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

test("selecting custom persists the palette for matching first paint and hydration after reload", () => {
  for (const config of [customTheme.DEFAULT_CUSTOM_THEME, { accent: "#315EFB", appearance: "dark" } as const]) {
    const state = browser("shenzhi", "system", true);
    if (config !== customTheme.DEFAULT_CUSTOM_THEME) {
      state.storage.set(customTheme.CUSTOM_THEME_STORAGE_KEY, JSON.stringify(config));
    }
    const { store, hydrate } = loadStore(state);
    hydrate();
    assert.equal(state.storage.has(customTheme.CUSTOM_THEME_VARS_STORAGE_KEY), false);

    store.getState().setPreset("custom");
    const expectedVariables = customTheme.createCustomThemeVariables(config);
    assert.equal(state.storage.get("shenzhi-theme-preset"), "custom");
    assert.deepEqual(JSON.parse(state.storage.get(customTheme.CUSTOM_THEME_STORAGE_KEY) ?? "null"), config);
    assert.deepEqual(JSON.parse(state.storage.get(customTheme.CUSTOM_THEME_VARS_STORAGE_KEY) ?? "null"), expectedVariables);
    assert.deepEqual(Object.fromEntries(state.properties), expectedVariables);

    // A reload has fresh DOM and Store state, retaining only localStorage.
    const reloaded = browser("shenzhi", "system", true);
    state.storage.forEach((value, key) => reloaded.storage.set(key, value));
    firstPaint(reloaded);
    const expectedDark = config.appearance === "dark";
    assert.equal(reloaded.root.dataset.theme, "custom");
    assert.equal(reloaded.classes.has("dark"), expectedDark);
    assert.deepEqual(Object.fromEntries(reloaded.properties), expectedVariables);

    const refreshed = loadStore(reloaded);
    assert.equal(refreshed.store.getState().preset, "shenzhi");
    refreshed.hydrate();
    assert.equal(refreshed.store.getState().preset, "custom");
    assert.equal(reloaded.root.dataset.theme, "custom");
    assert.equal(reloaded.classes.has("dark"), expectedDark);
    assert.deepEqual(Object.fromEntries(reloaded.properties), expectedVariables);
  }
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


test("teal preserves warm whites, neutral dark surfaces, and AA text contrast", () => {
  const light = tokens('html[data-theme="warm-teal"]');
  const dark = { ...light, ...tokens('html[data-theme="warm-teal"].dark') };
  assert.equal(light["--color-background"], "#fbfaf4");
  assert.equal(light["--color-primary"], "#1c7783");
  assert.equal(dark["--color-primary"], "#7bd4d8");
  for (const palette of [light, dark]) {
    for (const key of customTheme.CUSTOM_THEME_VARIABLES) assert.ok(palette[key], key);
    for (const surface of ["background", "sidebar", "card", "chip", "panel"]) {
      for (const text of ["ink", "ink-2", "muted", "faint"]) assert.ok(contrast(palette[`--color-${text}`], palette[`--color-${surface}`]) >= 4.5, `${text} on ${surface}`);
    }
    for (const action of ["primary", "primary-deep"]) assert.ok(contrast(palette["--color-primary-foreground"], palette[`--color-${action}`]) >= 4.5);
    assert.ok(contrast(palette["--color-primary"], palette["--color-primary-soft"]) >= 4.5);
  }
  for (const surface of ["background", "sidebar", "card", "chip", "panel", "line"]) {
    const value = dark[`--color-${surface}`];
    assert.equal(value.slice(1, 3), value.slice(3, 5), surface);
    assert.equal(value.slice(3, 5), value.slice(5, 7), surface);
  }
  assert.doesNotMatch(css, /@import[^;]*warm-teal/);
});

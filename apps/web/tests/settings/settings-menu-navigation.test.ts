import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";
import * as presets from "../../lib/theme-presets";

type Element = { type: unknown; props: Record<string, unknown> };
const jsx = (type: unknown, props: Element["props"]) => ({ type, props });
function elements(node: unknown): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!node || typeof node !== "object" || !("props" in node)) return [];
  const element = node as Element;
  return [element, ...elements(element.props.children)];
}
function load(path: string, dependencies: Record<string, unknown>, globals: Record<string, unknown> = {}) {
  const exports: Record<string, unknown> = {};
  runInNewContext(ts.transpileModule(readFileSync(path, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, {
    exports, ...globals,
    require: (id: string) => {
      assert.ok(id in dependencies, `Unexpected import: ${id}`);
      return dependencies[id];
    },
  });
  return exports;
}

test("quick theme buttons select their IDs; all links close and more colors scrolls on repeated navigation", () => {
  let selected = "custom";
  let closed = 0;
  let scrolled = 0;
  let expanded = 0;
  const state = { mode: "system", preset: selected, setMode: () => {}, setPreset: (id: string) => { selected = id; } };
  const loaded = load("components/common/layout/settings-menu.tsx", {
    react: { useId: () => "settings-menu", useSyncExternalStore: () => true },
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "next/link": { default: "a" },
    "next/navigation": { usePathname: () => "/settings" },
    "lucide-react": {},
    "@/lib/theme-presets": presets,
    "@/lib/utils": { cn: (...values: unknown[]) => values.filter(Boolean).join(" ") },
    "@/stores/theme": { useThemeStore: (selector: (value: typeof state) => unknown) => selector(state) },
    "@/stores/sidebar": { useSidebarStore: (selector: (value: unknown) => unknown) => selector({ setCollapsed: () => expanded++ }) },
    "@/features/settings/components/settings-tabs": {},
    "./use-settings-menu-hover": { useSettingsMenuHover: () => ({ open: true, close: () => closed++ }) },
  }, { document: { getElementById: (id: string) => id === "appearance" ? { scrollIntoView: () => scrolled++ } : null } });
  const menu = loaded.SettingsMenu as (props: { collapsed: boolean }) => unknown;
  for (const collapsed of [false, true]) {
    const tree = elements(menu({ collapsed }));
    const themes = tree.filter(({ type }) => type === "button");
    assert.equal(themes.length, 5, "old custom theme does not expose palette or mode controls");
    themes.forEach((button, index) => {
      (button.props.onClick as () => void)();
      assert.equal(selected, presets.QUICK_THEME_PRESET_IDS[index]);
    });
    const links = tree.filter(({ type }) => type === "a");
    assert.deepEqual(links.map(({ props }) => props.href), ["/settings", ...["profile", "subscription", "usage", "agent", "mcp", "api", "notifications"].map((tab) => `/settings?tab=${tab}`), "/settings?tab=profile#appearance"]);
    links.forEach(({ props }) => (props.onClick as () => void)());
    const more = links.at(-1)!;
    assert.equal(more.props.scroll, undefined);
    (more.props.onNavigate as () => void)();
    (more.props.onNavigate as () => void)();
  }
  assert.equal(closed, 18);
  assert.equal(scrolled, 4);
  assert.equal(expanded, 1, "collapsed settings trigger retains expansion behavior");
});

test("appearance scroll waits for the active profile panel, handles hash changes and cleans frames", () => {
  let tab = "notifications";
  let hash = "#appearance";
  let effect: (() => (() => void) | undefined) | undefined;
  let hashListener: (() => void) | undefined;
  let nextId = 0;
  let scrolled = 0;
  const frames = new Map<number, () => void>();
  const loaded = load("features/settings/components/settings-tabs.tsx", {
    react: { useEffect: (callback: typeof effect) => { effect = callback; } },
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "next/navigation": { useRouter: () => ({}), useSearchParams: () => ({ get: () => tab }) },
    "@/components/auth/auth-provider": { useAuth: () => ({ session: null }) },
    "@/components/ui/tabs": {},
    "../hooks/use-user-settings": { useUserSettings: () => ({ locale: "zh-CN" }) },
    "../i18n": { settingsMessages: { "zh-CN": {} } },
    "./account-section": {}, "./notifications-panel": {}, "./placeholder-panel": {}, "./profile-panel": {},
    "./tab-config": { isSettingsTab: () => true, SETTINGS_TABS: [] },
  }, {
    window: {
      location: { get hash() { return hash; } },
      addEventListener: (_name: string, callback: () => void) => { hashListener = callback; },
      removeEventListener: () => { hashListener = undefined; },
    },
    document: { getElementById: (id: string) => {
      assert.equal(id, "appearance");
      assert.equal(tab, "profile");
      return { scrollIntoView: () => scrolled++ };
    } },
    requestAnimationFrame: (callback: () => void) => { frames.set(++nextId, callback); return nextId; },
    cancelAnimationFrame: (id: number) => frames.delete(id),
  });
  const outer = (loaded.SettingsTabs as () => Element)();
  const render = outer.type as () => void;
  render(); effect!();
  assert.equal(frames.size, 0);
  tab = "profile";
  render(); const cleanup = effect!();
  assert.equal(scrolled, 0, "profile must commit before scrolling");
  assert.equal(frames.size, 1);
  for (const [id, callback] of frames) { frames.delete(id); callback(); }
  assert.equal(scrolled, 1);
  hashListener!();
  assert.equal(frames.size, 1);
  hash = ""; hashListener!();
  assert.equal(frames.size, 0);
  hash = "#appearance"; hashListener!();
  cleanup!();
  assert.equal(frames.size, 0);
  assert.equal(hashListener, undefined);
});

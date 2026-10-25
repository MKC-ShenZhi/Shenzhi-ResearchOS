import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import * as jsxRuntime from "react/jsx-runtime";
import ts from "typescript";
import type { KnowledgeConference } from "../../clients/knowledge/types";
import * as rotation from "../../features/knowledge/search/conferences/conference-state";

const conference = (name: string, paperCount = 1): KnowledgeConference => ({ name, paperCount, years: [2026, 2022], yearCount: 2 });
const items = [...rotation.FEATURED_CONFERENCES.map((name) => conference(name, 100)), ...Array.from({ length: 7 }, (_, index) => conference(`Other ${index}`, 7 - index))];

test("batches preserve all real records, stable order, aliases and a short final batch", () => {
  const records = [...items, conference("AAAI"), conference("AAAI alias"), { ...conference("Empty"), years: [] }];
  const before = JSON.stringify(records);
  const batches = rotation.buildConferenceBatches(records);
  assert.deepEqual(batches.map((batch) => batch.length), [6, 6, 3]);
  assert.deepEqual(batches[0].map((entry) => entry.conference.name), rotation.FEATURED_CONFERENCES);
  assert.equal(new Set(batches.flat().map((entry) => entry.key)).size, 15);
  assert.equal(batches.flat().filter((entry) => entry.conference.name === "AAAI").length, 2);
  assert.ok(batches.flat().some((entry) => entry.conference.name === "AAAI alias"));
  assert.deepEqual(rotation.buildConferenceBatches(records), batches);
  assert.equal(JSON.stringify(records), before);
  assert.deepEqual(rotation.buildConferenceBatches([]), []);
});

type Element = { type: unknown; key: string | null; props: Record<string, unknown> };
function elements(value: unknown): Element[] {
  if (Array.isArray(value)) return value.flatMap(elements);
  if (!value || typeof value !== "object" || !("props" in value)) return [];
  const element = value as Element;
  return [element, ...elements(element.props.children)];
}

/** Execute the real component with controlled effects and a deterministic browser clock. */
function carousel(initialItems = items, reducedMotion = false) {
  const source = ts.transpileModule(readFileSync("features/knowledge/search/conferences/conference-carousel.tsx", "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  let now = 0;
  let timerId = 0;
  const timers = new Map<number, { at: number; run: () => void }>();
  const listeners = new Set<() => void>();
  const document = { hidden: false, addEventListener: (_name: string, listener: () => void) => listeners.add(listener), removeEventListener: (_name: string, listener: () => void) => listeners.delete(listener) };
  const states: unknown[] = [];
  const effects: Array<{ deps: unknown[]; cleanup?: () => void }> = [];
  let stateCursor = 0;
  let effectCursor = 0;
  let scheduled: Array<() => void> = [];
  const useEffect = (effect: () => (() => void) | undefined, deps: unknown[]) => {
    const slot = effectCursor++;
    if (!effects[slot] || deps.some((value, index) => !Object.is(value, effects[slot].deps[index]))) scheduled.push(() => {
      effects[slot]?.cleanup?.();
      effects[slot] = { deps, cleanup: effect() };
    });
  };
  const dependencies: Record<string, unknown> = {
    "react/jsx-runtime": jsxRuntime,
    "react": {
      useState: (initial: unknown) => {
        const slot = stateCursor++;
        if (!(slot in states)) states[slot] = initial;
        return [states[slot], (value: unknown) => { states[slot] = typeof value === "function" ? value(states[slot]) : value; }];
      },
      useMemo: (factory: () => unknown) => factory(),
      useEffect,
      useSyncExternalStore: (subscribe: (callback: () => void) => () => void, getSnapshot: () => unknown) => {
        useEffect(() => subscribe(() => {}), [subscribe]);
        return getSnapshot();
      },
    },
    "framer-motion": { AnimatePresence: "presence", motion: { div: "motion-div" }, useReducedMotion: () => reducedMotion },
    "lucide-react": { ChevronRight: "svg", Pause: "svg", Play: "svg" },
    "./conference-state": rotation,
  };
  const exports: { ConferenceCarousel?: (props: { items: KnowledgeConference[]; onSelect: (item: KnowledgeConference) => void }) => unknown } = {};
  runInNewContext(source, {
    exports, document,
    window: { setTimeout: (run: () => void, delay: number) => { timers.set(++timerId, { at: now + delay, run }); return timerId; }, clearTimeout: (id: number) => timers.delete(id) },
    require: (id: string) => { assert.ok(id in dependencies, `Unexpected carousel dependency: ${id}`); return dependencies[id]; },
  });
  const selected: KnowledgeConference[] = [];
  let currentItems = initialItems;
  let tree: unknown;
  const render = () => {
    stateCursor = 0; effectCursor = 0; scheduled = [];
    tree = exports.ConferenceCarousel!({ items: currentItems, onSelect: (item) => selected.push(item) });
    scheduled.forEach((effect) => effect());
  };
  render();
  const all = () => elements(tree);
  const call = (element: Element, name: string, arg?: unknown) => {
    (element.props[name] as (arg?: unknown) => void)(arg);
    render();
  };
  return {
    selected, timers, listeners,
    cards: () => all().filter((element) => String(element.props["aria-label"]).startsWith("选择会议 ")),
    motion: () => all().find((element) => element.type === "motion-div")!,
    feedback: () => all().filter((element) => element.props["data-selection-feedback"] === "true"),
    click: (name: string) => call(all().find((element) => element.props["aria-label"] === name)!, "onClick"),
    pointer: (inside: boolean) => call(all()[0], inside ? "onPointerEnter" : "onPointerLeave", { pointerType: "mouse" }),
    focus: (inside: boolean, keyboard = true) => call(all()[0], inside ? "onFocusCapture" : "onBlurCapture", { target: { matches: () => keyboard }, currentTarget: { contains: () => false }, relatedTarget: null }),
    hide: (hidden: boolean) => { document.hidden = hidden; listeners.forEach((listener) => listener()); render(); },
    update: (next: KnowledgeConference[]) => { currentItems = next; render(); },
    tick: (ms: number) => {
      const end = now + ms;
      while (true) {
        const next = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        now = next[1].at; timers.delete(next[0]); next[1].run(); render();
      }
      now = end;
    },
    unmount: () => effects.forEach((effect) => effect.cleanup?.()),
  };
}

test("every 15 seconds advances all six, then the short tail, then the first batch without selecting", () => {
  const view = carousel();
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 AAAI");
  view.tick(14_999);
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 AAAI");
  view.tick(1);
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 Other 0");
  assert.equal(view.cards().length, 6);
  view.tick(15_000);
  assert.equal(view.cards().length, 1);
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 Other 6");
  view.tick(15_000);
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 AAAI");
  assert.deepEqual(view.selected, []);
  view.unmount();
  assert.equal(view.timers.size, 0);
  assert.equal(view.listeners.size, 0);
});

test("a click selects once with 800ms feedback, while later batches never change the chosen conference", () => {
  const view = carousel();
  view.click("选择会议 CVPR");
  assert.equal(view.feedback().length, 1);
  assert.equal(view.selected[0].name, "CVPR");
  view.tick(799);
  view.click("选择会议 CVPR"); // Repeated activation restarts the feedback timer.
  view.tick(799);
  assert.equal(view.feedback().length, 1);
  view.tick(1);
  assert.equal(view.feedback().length, 0);
  view.tick(60_000);
  assert.deepEqual(view.selected.map((item) => item.name), ["CVPR", "CVPR"]);
  view.unmount();
});

test("hover, keyboard focus, explicit pause and hidden tabs suspend and restart a full 15 seconds", () => {
  const view = carousel();
  for (const pause of [view.pointer, (inside: boolean) => view.focus(inside), view.hide]) {
    view.tick(14_000); pause(true); view.tick(30_000);
    assert.equal(view.cards()[0].props["aria-label"], "选择会议 AAAI");
    pause(false); view.tick(14_999);
    assert.equal(view.cards()[0].props["aria-label"], "选择会议 AAAI");
    view.click("下一批会议"); view.click("下一批会议"); view.click("下一批会议"); // Reset to the first batch and restart the interval.
  }
  view.click("暂停自动轮换"); view.tick(60_000);
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 AAAI");
  view.click("下一批会议");
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 Other 0");
  view.click("恢复自动轮换"); view.tick(15_000);
  assert.equal(view.cards().length, 1);
  view.unmount();
});

test("mouse activation does not leave rotation permanently paused after the pointer exits", () => {
  const view = carousel();
  view.pointer(true); view.focus(true, false); view.click("选择会议 CVPR");
  view.pointer(false); view.tick(15_000);
  assert.equal(view.cards()[0].props["aria-label"], "选择会议 Other 0");
  assert.equal(view.selected[0].name, "CVPR");
  view.unmount();
});

test("single/empty batches do not schedule rotation; catalog shrink remains valid; reduced motion removes sliding", () => {
  const view = carousel();
  view.click("下一批会议"); view.click("下一批会议");
  view.update(items.slice(0, 2));
  assert.equal(view.cards().length, 2);
  assert.equal(view.timers.size, 0);
  view.update([]);
  assert.equal(view.cards().length, 0);
  view.unmount();
  const reduced = carousel(items, true);
  assert.equal((reduced.motion().props.transition as { duration: number }).duration, 0);
  assert.equal((reduced.motion().props.initial as { y: number }).y, 0);
  reduced.unmount();
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";
import * as geometry from "../../components/common/layout/settings-menu-hover";
import type { useSettingsMenuHover } from "../../components/common/layout/use-settings-menu-hover";

type Hover = ReturnType<typeof useSettingsMenuHover>;
class Target {
  constructor(public inside = false, public control = false, public keyboard = false) {}
  closest() { return this.control ? this : null; }
  matches() { return this.keyboard; }
}

// Exercise the real hook with the repository's existing VM approach, a small DOM
// boundary and a deterministic clock, without installing a browser test framework.
function harness() {
  const cells: unknown[] = [];
  const effects = new Map<number, { deps: unknown[]; cleanup?: () => void }>();
  const timers = new Map<number, { at: number; callback: () => void }>();
  const listeners = new Map<string, Set<(event: unknown) => void>>();
  let cursor = 0;
  let now = 0;
  let timerId = 0;
  let disabled = false;
  let mounted = true;
  let lateUpdates = 0;
  let focused: Target | null = null;
  let rect = { left: 240, right: 448, top: 160, bottom: 640 };
  const root = { contains: (target: Target | null) => !!target?.inside };
  const trigger = new Target(true);
  Object.assign(trigger, { focus: () => { focused = trigger; } });
  const react = {
    useState: (initial: unknown) => {
      const index = cursor++;
      if (!(index in cells)) cells[index] = initial;
      return [cells[index], (value: unknown) => { if (!mounted) lateUpdates++; cells[index] = value; }];
    },
    useRef: (initial: unknown) => {
      const index = cursor++;
      if (!(index in cells)) cells[index] = { current: initial };
      return cells[index];
    },
    useCallback: (callback: unknown, deps: unknown[]) => {
      const index = cursor++;
      const previous = cells[index] as { callback: unknown; deps: unknown[] } | undefined;
      if (!previous || !deps.every((dep, i) => dep === previous.deps[i])) cells[index] = { callback, deps };
      return (cells[index] as { callback: unknown }).callback;
    },
    useEffect: (effect: () => (() => void) | undefined, deps: unknown[]) => {
      const index = cursor++;
      const previous = effects.get(index);
      if (previous && deps.every((dep, i) => dep === previous.deps[i])) return;
      previous?.cleanup?.();
      effects.set(index, { deps, cleanup: effect() });
    },
  };
  const events = {
    addEventListener: (name: string, callback: (event: unknown) => void) => {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name)!.add(callback);
    },
    removeEventListener: (name: string, callback: (event: unknown) => void) => listeners.get(name)?.delete(callback),
  };
  const exports: { useSettingsMenuHover?: typeof useSettingsMenuHover } = {};
  runInNewContext(ts.transpileModule(readFileSync("components/common/layout/use-settings-menu-hover.ts", "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, {
    exports,
    require: (id: string) => {
      if (id === "react") return react;
      if (id === "./settings-menu-hover") return geometry;
      throw new Error(`Unexpected import: ${id}`);
    },
    Element: Target,
    Date: { now: () => now },
    document: { ...events, get activeElement() { return focused; } },
    window: events,
    setTimeout: (callback: () => void, delay: number) => { const id = ++timerId; timers.set(id, { at: now + delay, callback }); return id; },
    clearTimeout: (id: number) => timers.delete(id),
  });
  function render() {
    cursor = 0;
    const hover = exports.useSettingsMenuHover!(disabled);
    hover.rootRef.current = root as unknown as HTMLDivElement;
    hover.triggerRef.current = trigger as unknown as HTMLAnchorElement;
    hover.menuRef.current = { getBoundingClientRect: () => rect } as HTMLDivElement;
    return hover;
  }
  const pointer = (x: number, y: number, pointerType = "mouse") => ({ clientX: x, clientY: y, pointerType }) as Parameters<Hover["onPointerLeave"]>[0];
  function emit(name: string, event: unknown = {}) {
    listeners.get(name)?.forEach((callback) => callback(event));
    return render();
  }
  render();
  return {
    render, timers, listeners,
    enter: (pointerType = "mouse") => { render().onPointerEnter(pointer(120, 620, pointerType)); return render(); },
    leave: (x = 120, y = 600) => { render().onPointerLeave(pointer(x, y)); return render(); },
    move: (x: number, y: number, target = new Target()) => emit("pointermove", { clientX: x, clientY: y, target, pointerType: "mouse" }),
    advance: (ms: number) => {
      const end = now + ms;
      while (true) {
        const next = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
        if (!next || next[1].at > end) break;
        now = next[1].at;
        timers.delete(next[0]);
        next[1].callback();
        render();
      }
      now = end;
      return render();
    },
    focus: (keyboard: boolean) => { focused = new Target(true, true, keyboard); render().onFocus(); return render(); },
    blur: () => { focused = null; render().onBlur({ relatedTarget: null } as Parameters<Hover["onBlur"]>[0]); return render(); },
    emit,
    setRect: (value: typeof rect) => { rect = value; },
    disable: () => { disabled = true; return render(); },
    unmount: () => { mounted = false; effects.forEach(({ cleanup }) => cleanup?.()); },
    lateUpdates: () => lateUpdates,
  };
}

test("horizontal entry cancels closing; repeated entry has no duplicate timers or listeners", () => {
  const h = harness();
  assert.ok(h.enter().open);
  h.leave(232, 620);
  assert.equal(h.timers.size, 1);
  h.move(237, 620);
  assert.ok(h.enter().open);
  assert.ok(h.advance(1000).open);
  for (let i = 0; i < 10; i++) { h.leave(); h.enter(); }
  assert.equal(h.timers.size, 0);
  for (const callbacks of h.listeners.values()) assert.ok(callbacks.size <= 1);
});

test("slow diagonal movement to the top of the menu outlives the initial close delay", () => {
  const h = harness();
  h.enter();
  h.leave();
  for (let step = 1; step <= 10; step++) {
    h.advance(180);
    assert.ok(h.move(120 + step * 12, 600 - step * 42).open, `step ${step}`);
  }
  assert.ok(h.enter().open, "arrival at profile cancels corridor protection");
  assert.ok(h.advance(1000).open);
});

test("fractional pointer progress accumulates instead of expiring slow motion", () => {
  const h = harness(); h.enter(); h.leave();
  for (let step = 1; step <= 40; step++) {
    h.advance(30);
    assert.ok(h.move(120 + step * 0.5, 600 - step).open);
  }
});

test("diagonal intent may cross other sidebar links without closing, but never blocks their clicks", () => {
  const h = harness(); h.enter(); h.leave();
  const otherLink = new Target(false, true);
  for (let step = 1; step <= 9; step++) {
    h.advance(180);
    assert.ok(h.move(120 + step * 12, 600 - step * 42, otherLink).open, `crossing link at step ${step}`);
  }
  assert.equal(h.emit("pointerdown", { target: otherLink }).open, false);

  const paused = harness(); paused.enter(); paused.leave();
  assert.ok(paused.move(132, 558, otherLink).open);
  assert.equal(paused.advance(800).open, false, "stopping on another navigation ends protection");
});

test("an approach may overshoot Profile before ever entering the menu, then correct downward", () => {
  const h = harness(); h.enter(); h.leave();
  for (let step = 1; step <= 9; step++) {
    h.advance(100);
    assert.ok(h.move(120 + step * 12, 600 - step * 48).open);
  }
  assert.ok(h.move(270, 125).open, "35px above the menu is protected across its full width");
  assert.ok(h.advance(400).open);
  assert.ok(h.move(270, 150).open, "downward correction does not count as moving away");
  h.enter();
  assert.ok(h.advance(1000).open, "reentry cancels the overshoot deadline");
  assert.equal(h.timers.size, 0);
});

test("leaving above the menu permits a brief correction in expanded/collapsed and scaled layouts", () => {
  for (const scale of [0.9, 1]) {
    for (const left of [72, 240]) {
      const h = harness();
      h.setRect({ left: left * scale, right: (left + 208) * scale, top: 160 * scale, bottom: 640 * scale });
      h.enter(); h.leave((left + 40) * scale, 156 * scale);
      assert.ok(h.move((left + 80) * scale, 124 * scale).open);
      assert.ok(h.advance(500).open);
      assert.ok(h.move((left + 70) * scale, 150 * scale).open);
      h.enter();
      assert.ok(h.advance(1000).open);
    }
  }
});

test("overshoot protection is bounded in space and time and never blocks outside clicks", () => {
  for (const [x, y] of [[300, 111], [465, 140], [223, 140]]) {
    const h = harness(); h.enter(); h.leave(300, 150);
    assert.equal(h.move(x, y).open, false);
  }
  const jitter = harness(); jitter.enter(); jitter.leave(300, 150);
  for (let step = 0; step < 3; step++) {
    jitter.advance(200);
    assert.ok(jitter.move(300 + step % 2, 130 + step % 2).open);
  }
  assert.equal(jitter.advance(200).open, false, "jitter does not extend the initial 800ms budget");
  const stationary = harness(); stationary.enter(); stationary.leave(300, 150);
  assert.equal(stationary.advance(800).open, false, "no pointermove is needed to expire protection");
  const clicked = harness(); clicked.enter(); clicked.leave(300, 150);
  assert.equal(clicked.emit("pointerdown", { target: new Target(false, true) }).open, false);
  assert.equal(clicked.timers.size, 0);
});

test("unrelated controls, reversed movement, inactivity and deadline all close the menu", () => {
  for (const unrelated of [new Target(false, true), new Target()]) {
    const h = harness();
    h.enter(); h.leave();
    assert.equal(h.move(100, 500, unrelated).open, false);
  }
  const reverse = harness();
  reverse.enter(); reverse.leave(); reverse.move(180, 400);
  assert.equal(reverse.move(160, 410).open, false);
  const idle = harness();
  idle.enter(); idle.leave();
  assert.ok(idle.advance(300).open);
  assert.equal(idle.advance(500).open, false);
  const deadline = harness();
  deadline.enter(); deadline.leave();
  for (let i = 1; i <= 24; i++) { deadline.advance(200); deadline.move(120 + i * 2, 600 - i * 4); }
  assert.equal(deadline.advance(200).open, false);
});

test("keyboard focus survives pointer leave, while mouse focus cannot pin the menu", () => {
  const h = harness();
  h.focus(true); h.leave();
  assert.ok(h.advance(1000).open);
  h.blur();
  assert.equal(h.advance(300).open, false);
  h.enter(); h.focus(false); h.leave();
  assert.equal(h.move(20, 20).open, false);
  h.focus(true);
  assert.equal(h.emit("keydown", { key: "Escape" }).open, false);
});

test("outside click, resize and window blur close; touch/mobile do not open hover", () => {
  for (const event of ["resize", "blur", "pointerdown"]) {
    const h = harness(); h.enter(); h.leave();
    assert.equal(h.emit(event, { target: new Target() }).open, false);
    assert.equal(h.timers.size, 0);
  }
  const h = harness();
  assert.equal(h.enter("touch").open, false);
  h.disable();
  assert.equal(h.enter().open, false);
});

test("real geometry scales with expanded/collapsed layouts and 90% / 100% coordinates", () => {
  for (const scale of [0.9, 1]) {
    for (const left of [72, 240]) {
      const h = harness();
      h.setRect({ left: left * scale, right: (left + 208) * scale, top: 160 * scale, bottom: 640 * scale });
      h.enter(); h.leave((left - 50) * scale, 600 * scale);
      h.advance(250);
      assert.ok(h.move((left - 25) * scale, 400 * scale).open);
      h.advance(250);
      assert.ok(h.move((left - 2) * scale, 190 * scale).open);
    }
  }
});

test("unmount cancels timers and every global listener without late updates", () => {
  const h = harness(); h.enter(); h.leave(); h.unmount();
  assert.equal(h.timers.size, 0);
  for (const callbacks of h.listeners.values()) assert.equal(callbacks.size, 0);
  h.advance(6000);
  assert.equal(h.lateUpdates(), 0);
});

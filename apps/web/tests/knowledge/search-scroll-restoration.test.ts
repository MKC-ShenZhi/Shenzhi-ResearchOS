import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import React, { type MouseEvent } from "react";
import { clearSearchScroll, readSearchScroll, saveSearchScroll } from "../../features/knowledge/search/search-scroll-state";
import { discardSearchScroll, rememberSearchScroll, useSearchScrollRestoration } from "../../features/knowledge/search/use-search-scroll-restoration";

const source = "/knowledge/search?q=robot&page=2&venue=RSS";

function browser(t: TestContext) {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
  const frames = new Map<number, FrameRequestCallback>();
  const listeners = new Map<string, Set<(event: { key?: string }) => void>>();
  const scrolls: ScrollToOptions[] = [];
  let frameId = 0;
  const win = {
    sessionStorage: storage,
    scrollY: 1250,
    location: { origin: "https://local.test" },
    scrollTo: (options: ScrollToOptions) => { scrolls.push(options); },
    requestAnimationFrame: (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; },
    cancelAnimationFrame: (id: number) => { frames.delete(id); },
    addEventListener: (type: string, callback: (event: { key?: string }) => void) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(callback);
    },
    removeEventListener: (type: string, callback: (event: { key?: string }) => void) => { listeners.get(type)?.delete(callback); },
  };
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { value: win, configurable: true });
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  });
  let cleanup: (() => void) | void;
  t.mock.method(React, "useEffect", (effect: React.EffectCallback) => { cleanup = effect(); });
  return {
    storage, scrolls, win,
    mount: (ready: boolean, path = source) => {
      // eslint-disable-next-line react-hooks/rules-of-hooks -- The harness drives the captured effect lifecycle explicitly.
      useSearchScrollRestoration(path, ready);
      return () => { if (typeof cleanup === "function") cleanup(); };
    },
    frame: () => {
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach((callback) => callback(0));
    },
    dispatch: (type: string, key?: string) => { listeners.get(type)?.forEach((callback) => callback({ key })); },
    click: (path: string, overrides = {}) => ({
      button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, defaultPrevented: false,
      target: { closest: () => ({ href: `https://local.test${path}`, target: "", hasAttribute: () => false }) },
      ...overrides,
    } as unknown as MouseEvent<HTMLElement>),
  };
}

test("cold results do not restore until rendered; a consumed position is not replayed", (t) => {
  const b = browser(t);
  saveSearchScroll(b.storage, source, 1250);
  const unmountLoading = b.mount(false);
  b.frame(); b.frame();
  assert.deepEqual(b.scrolls, []);
  unmountLoading();
  const unmountReady = b.mount(true);
  b.frame();
  assert.deepEqual(b.scrolls, []);
  b.frame();
  assert.deepEqual(b.scrolls, [{ top: 1250, behavior: "instant" }]);
  assert.equal(readSearchScroll(b.storage, source), null);
  unmountReady();
  const unmountAgain = b.mount(true);
  b.frame(); b.frame();
  assert.equal(b.scrolls.length, 1);
  unmountAgain();
});

test("user scrolling while results load cancels deferred restoration", (t) => {
  const b = browser(t);
  saveSearchScroll(b.storage, source, 1250);
  const unmount = b.mount(false);
  b.dispatch("wheel");
  unmount();
  const unmountReady = b.mount(true);
  b.frame(); b.frame();
  assert.deepEqual(b.scrolls, []);
  unmountReady();
});

test("keyboard scrolling cancels scheduled restoration and unmount cancels animation frames", (t) => {
  const b = browser(t);
  saveSearchScroll(b.storage, source, 1250);
  const unmount = b.mount(true);
  b.frame();
  b.dispatch("keydown", "PageDown");
  b.frame();
  assert.deepEqual(b.scrolls, []);
  unmount();
  saveSearchScroll(b.storage, source, 1250);
  b.mount(true)();
  b.frame(); b.frame();
  assert.deepEqual(b.scrolls, []);
});

test("detail and graph links save the source position; other actions and new tabs do not", (t) => {
  const b = browser(t);
  for (const path of ["/papers/opaque%2Fid", "/papers/id/graph?returnTo=source"]) {
    rememberSearchScroll(b.click(path), source);
    assert.equal(readSearchScroll(b.storage, source), 1250);
    clearSearchScroll(b.storage, source);
  }
  for (const event of [b.click("/knowledge/search?q=new"), b.click("/papers/id", { ctrlKey: true }),
    b.click("/papers/id", { button: 1 }), b.click("/papers/id", { defaultPrevented: true })]) {
    rememberSearchScroll(event, source);
    assert.equal(readSearchScroll(b.storage, source), null);
  }
});

test("new searches, filters and pagination can invalidate restoration before the next paint", (t) => {
  const b = browser(t);
  saveSearchScroll(b.storage, source, 1250);
  const unmount = b.mount(true);
  b.frame();
  discardSearchScroll(source);
  b.frame();
  assert.deepEqual(b.scrolls, []);
  unmount();
});

test("blocked session storage access still allows navigation and rendering", (t) => {
  const b = browser(t);
  Object.defineProperty(b.win, "sessionStorage", { get: () => { throw new Error("SecurityError"); } });
  assert.doesNotThrow(() => rememberSearchScroll(b.click("/papers/id"), source));
  assert.doesNotThrow(() => b.mount(true)());
});

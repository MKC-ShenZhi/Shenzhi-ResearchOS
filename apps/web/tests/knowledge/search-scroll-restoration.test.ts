import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { AppRouterContext, type AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { usePaperCardNavigation } from "../../components/common/use-paper-card-navigation";
import { createSearchRestoration } from "../../lib/navigation/search-restoration";
import { readKnowledgeSearchUrlState } from "../../features/knowledge/search/search-url-state";
import React, { type KeyboardEvent, type MouseEvent } from "react";
import { clearSearchScroll, readSearchScroll, saveSearchScroll } from "../../features/knowledge/search/search-scroll-state";
import { discardSearchScroll, rememberSearchScroll, saveCurrentSearchScroll, useSearchScrollRestoration } from "../../features/knowledge/search/use-search-scroll-restoration";

const source = "/knowledge/search?q=robot&page=2&venue=RSS";

function browser(t: TestContext) {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
  const frames = new Map<number, FrameRequestCallback>();
  const listeners = new Map<string, Set<(event: { key?: string; defaultPrevented?: boolean }) => void>>();
  const scrolls: ScrollToOptions[] = [];
  let frameId = 0;
  const win = {
    sessionStorage: storage,
    scrollY: 1250,
    location: { origin: "https://local.test" },
    scrollTo: (options: ScrollToOptions) => { scrolls.push(options); },
    requestAnimationFrame: (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; },
    cancelAnimationFrame: (id: number) => { frames.delete(id); },
    addEventListener: (type: string, callback: (event: { key?: string; defaultPrevented?: boolean }) => void) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(callback);
    },
    removeEventListener: (type: string, callback: (event: { key?: string; defaultPrevented?: boolean }) => void) => { listeners.get(type)?.delete(callback); },
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
    mount: (ready: boolean, path = source, scope: string | null = "anonymous") => {
      // eslint-disable-next-line react-hooks/rules-of-hooks -- The harness drives the captured effect lifecycle explicitly.
      useSearchScrollRestoration(path, ready, scope);
      return () => { if (typeof cleanup === "function") cleanup(); };
    },
    frame: () => {
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach((callback) => callback(0));
    },
    dispatch: (type: string, key?: string, defaultPrevented = false) => {
      listeners.get(type)?.forEach((callback) => callback({ key, defaultPrevented }));
    },
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

test("directory conference activation restores its exact filtered page once, independently of keyword results", (t) => {
  const b = browser(t);
  const directory = "/knowledge/search/conferences?q=robot&page=2&sort=name";
  const destination = "/knowledge/search?mode=conference&conference=RSS&year=2025";
  rememberSearchScroll(b.click(destination), directory);
  assert.equal(readSearchScroll(b.storage, directory), 1250);
  assert.equal(readSearchScroll(b.storage, "/knowledge/search?q=robot&page=2"), null);
  const unmount = b.mount(true, directory);
  b.frame(); b.frame();
  assert.deepEqual(b.scrolls, [{ top: 1250, behavior: "instant" }]);
  assert.equal(readSearchScroll(b.storage, directory), null);
  unmount();
  rememberSearchScroll(b.click(destination, { ctrlKey: true }), directory);
  rememberSearchScroll(b.click("/knowledge/search?mode=keyword"), directory);
  assert.equal(readSearchScroll(b.storage, directory), null);
});

test("blocked session storage access still allows navigation and rendering", (t) => {
  const b = browser(t);
  Object.defineProperty(b.win, "sessionStorage", { get: () => { throw new Error("SecurityError"); } });
  assert.doesNotThrow(() => rememberSearchScroll(b.click("/papers/id"), source));
  assert.doesNotThrow(() => b.mount(true)());
});


test("restoring a sidebar URL preserves its query, filters and page while consuming only scroll", (t) => {
  const b = browser(t);
  const navigation = createSearchRestoration(() => b.storage);
  navigation.record("anonymous", source);
  rememberSearchScroll(b.click("/papers/id"), source);
  navigation.record("anonymous", "/papers/id");
  const href = navigation.getHref("anonymous", "/knowledge/search");
  assert.equal(href, source);
  const state = readKnowledgeSearchUrlState(new URL(href, "https://local.test").searchParams);
  assert.equal(state.query, "robot");
  assert.equal(state.page, 2);
  assert.deepEqual(state.filters.venue, ["RSS"]);
  const unmount = b.mount(true, href);
  b.frame(); b.frame();
  assert.deepEqual(b.scrolls, [{ top: 1250, behavior: "instant" }]);
  assert.equal(navigation.getHref("anonymous", "/knowledge/search"), source);
  unmount();
  // Active clear keeps both mechanisms cleared on a later bare visit.
  navigation.clear("anonymous", "/knowledge/search");
  discardSearchScroll(source);
  navigation.record("anonymous", "/knowledge/search");
  assert.equal(navigation.getHref("anonymous", "/knowledge/search"), "/knowledge/search");
  assert.equal(readSearchScroll(b.storage, source), null);
});

test("auth pending and other identities cannot consume a user's pending scroll", (t) => {
  const b = browser(t);
  saveSearchScroll(b.storage, source, 1250, Date.now(), "user:alice");
  for (const scope of [null, "anonymous", "user:bob"]) {
    const unmount = b.mount(true, source, scope);
    b.frame(); b.frame();
    assert.deepEqual(b.scrolls, []);
    unmount();
  }
  const unmount = b.mount(true, source, "user:alice");
  b.frame(); b.frame();
  assert.deepEqual(b.scrolls, [{ top: 1250, behavior: "instant" }]);
  unmount();
});

test("card pointer and keyboard navigation save scroll only for actual same-tab activation", (t) => {
  const b = browser(t);
  const pushes: string[] = [];
  Object.assign(b.win, { getSelection: () => null, open: () => {} });
  class CardElement {
    contains(target: unknown) { return target === this; }
    closest() { return this; }
  }
  const previous = Object.getOwnPropertyDescriptor(globalThis, "Element");
  Object.defineProperty(globalThis, "Element", { value: CardElement, configurable: true });
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, "Element", previous);
    else Reflect.deleteProperty(globalThis, "Element");
  });
  const target = new CardElement();
  let card!: ReturnType<typeof usePaperCardNavigation>;
  function CardHarness() {
    card = usePaperCardNavigation("/papers/id", "Paper", () => saveCurrentSearchScroll(source, "anonymous"));
    return null;
  }
  renderToStaticMarkup(React.createElement(AppRouterContext.Provider, {
    value: { push: (href: string) => { pushes.push(href); } } as unknown as AppRouterInstance,
  }, React.createElement(CardHarness)));
  const click = (overrides = {}) => ({
    button: 0, defaultPrevented: false, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false,
    target, currentTarget: target, ...overrides,
  } as unknown as MouseEvent<HTMLElement>);
  card.onClick(click());
  assert.equal(readSearchScroll(b.storage, source), 1250);
  clearSearchScroll(b.storage, source);
  for (const overrides of [{ ctrlKey: true }, { button: 1 }, { defaultPrevented: true }, { target: {} }]) {
    card.onClick(click(overrides));
    assert.equal(readSearchScroll(b.storage, source), null);
  }
  card.onKeyDown({ ...click(), key: "Enter", repeat: false, preventDefault() {} } as unknown as KeyboardEvent<HTMLElement>);
  assert.equal(readSearchScroll(b.storage, source), 1250);
  assert.deepEqual(pushes, ["/papers/id", "/papers/id"]);
});

test("explicit search/filter/page actions invalidate both source and destination scroll records", () => {
  // Guard the actual handlers: a stale record at the destination must not replay on a new search.
  const page = readFileSync("features/knowledge/search/KnowledgeSearchPage.tsx", "utf8");
  for (const handler of ["submitSearch", "updateFilters", "updatePage"]) {
    const body = page.split(`const ${handler} = `)[1].split("\n  };")[0];
    assert.match(body, /discardSearchScroll\(returnTo, scope\)/);
    assert.match(body, /discardSearchScroll\(buildKnowledgeSearchUrl\(/);
  }
  assert.match(page, /if \(!text\) clearRestoration\(\)/);
  const results = readFileSync("features/knowledge/search/components/results-section.tsx", "utf8");
  assert.match(results, /onNavigate=\{\(\) => saveCurrentSearchScroll\(returnTo, scope\)\}/);
});


test("a prevented Space activation is not mistaken for manual scrolling", (t) => {
  const b = browser(t);
  saveSearchScroll(b.storage, source, 1250);
  const unmount = b.mount(true);
  b.dispatch("keydown", " ", true);
  b.frame(); b.frame();
  assert.deepEqual(b.scrolls, [{ top: 1250, behavior: "instant" }]);
  unmount();
});

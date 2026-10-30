"use client";

import { useSyncExternalStore } from "react";

interface ClockStore {
  subscribe: (onChange: () => void) => () => void;
  getSnapshot: () => number;
}

const stores = new Map<number, ClockStore>();
// Cards are fetched on the client, so the server snapshot only needs to be stable.
const SERVER_NOW = Date.now();
const getServerSnapshot = () => SERVER_NOW;

function createClockStore(intervalMs: number): ClockStore {
  let now = Date.now();
  let timer: number | undefined;
  const listeners = new Set<() => void>();
  return {
    subscribe(onChange) {
      listeners.add(onChange);
      if (timer === undefined) {
        now = Date.now();
        timer = window.setInterval(() => {
          now = Date.now();
          listeners.forEach((listener) => listener());
        }, intervalMs);
      }
      return () => {
        listeners.delete(onChange);
        if (listeners.size === 0) {
          window.clearInterval(timer);
          timer = undefined;
        }
      };
    },
    getSnapshot: () => now,
  };
}

function clockStore(intervalMs: number): ClockStore {
  let store = stores.get(intervalMs);
  if (!store) {
    store = createClockStore(intervalMs);
    stores.set(intervalMs, store);
  }
  return store;
}

/**
 * One shared clock per interval: the browser owns a single timer per granularity and
 * only the components that read it re-render. A per-second countdown therefore does
 * not re-render its card (and the card's layout animation) every tick.
 */
export function useNow(intervalMs = 1000): number {
  const store = clockStore(intervalMs);
  return useSyncExternalStore(store.subscribe, store.getSnapshot, getServerSnapshot);
}

"use client";

import { useEffect, useState } from "react";

/**
 * One shared clock for the whole list: the browser owns a single interval and
 * passes `now` down, instead of every countdown starting its own timer.
 */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);

  return now;
}

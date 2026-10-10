"use client";

import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";

const SEARCH_DEBOUNCE_MS = 250;

export function TopicSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [draftValue, setDraftValue] = useState(value);
  const composingRef = useRef(false);
  const skipNextDebounceRef = useRef(false);
  const onChangeRef = useRef(onChange);
  const debounceTimerRef = useRef<number | null>(null);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    // Keep browser back/forward navigation in sync with the local draft.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraftValue(value);
  }, [value]);

  useEffect(() => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    if (skipNextDebounceRef.current) {
      skipNextDebounceRef.current = false;
      return;
    }
    if (composingRef.current || draftValue === value) return;
    debounceTimerRef.current = window.setTimeout(() => {
      debounceTimerRef.current = null;
      onChangeRef.current(draftValue);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (debounceTimerRef.current !== null) {
        window.clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
  }, [draftValue, value]);

  const clearSearch = () => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    skipNextDebounceRef.current = true;
    setDraftValue("");
    onChangeRef.current("");
  };

  const startComposition = () => {
    composingRef.current = true;
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  };

  return (
    <div className="relative w-full">
      <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={draftValue}
        onChange={(event) => setDraftValue(event.target.value)}
        onCompositionStart={startComposition}
        onCompositionEnd={(event) => {
          composingRef.current = false;
          setDraftValue(event.currentTarget.value);
        }}
        placeholder="搜索主题"
        aria-label="搜索主题"
        className="h-12 rounded-full border-slate-200 bg-slate-50/70 pl-12 pr-12 text-base shadow-none transition focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-primary/20"
      />
      {draftValue ? <button type="button" onClick={clearSearch} aria-label="清除搜索" className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"><X className="size-4" /></button> : null}
    </div>
  );
}

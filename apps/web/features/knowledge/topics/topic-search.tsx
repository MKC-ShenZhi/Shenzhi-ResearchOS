"use client";

import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";

export function TopicSearch({ value, onSearch }: { value: string; onSearch: (value: string) => void }) {
  const [draftValue, setDraftValue] = useState(value);
  const composingRef = useRef(false);

  useEffect(() => {
    // Keep browser back/forward navigation in sync with the local draft.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraftValue(value);
  }, [value]);

  const clearSearch = () => {
    setDraftValue("");
    onSearch("");
  };

  const submitSearch = () => {
    if (composingRef.current) return;
    onSearch(draftValue);
  };

  return (
    <form className="relative w-full" role="search" onSubmit={(event) => { event.preventDefault(); submitSearch(); }}>
      <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={draftValue}
        onChange={(event) => setDraftValue(event.target.value)}
        onCompositionStart={() => { composingRef.current = true; }}
        onCompositionEnd={() => { composingRef.current = false; }}
        onKeyDown={(event) => { if (event.key === "Enter" && composingRef.current) event.preventDefault(); }}
        type="text"
        placeholder="搜索主题"
        aria-label="搜索主题"
        className="h-12 rounded-full border-slate-200 bg-slate-50/70 pl-12 pr-28 text-base shadow-none transition focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-primary/20"
      />
      <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
        {draftValue ? <button type="button" onClick={clearSearch} aria-label="清除搜索" className="rounded-full p-2 text-muted-foreground hover:text-foreground"><X className="size-4" /></button> : null}
        <button type="submit" aria-label="搜索" className="rounded-full p-2 text-primary hover:bg-primary/10"><Search className="size-4" /></button>
      </div>
    </form>
  );
}

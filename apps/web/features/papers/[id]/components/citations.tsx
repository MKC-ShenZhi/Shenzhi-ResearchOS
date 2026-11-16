"use client";

import { createContext, useContext, useRef, useState, type ReactNode } from "react";
import { isKnownCitation } from "./citation-validation";

const CitationContext = createContext<{
  active: number;
  jump: (id: number, target: "source" | "text") => void;
  validIds: ReadonlySet<string>;
}>({ active: 0, jump: () => {}, validIds: new Set() });

/** B's bidirectional citations, scoped to ONE assistant turn. */
export function CitationScope({
  children,
  referenceIds = [],
}: {
  children: ReactNode;
  referenceIds?: Array<string | number>;
}) {
  const root = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const validIds = new Set(referenceIds.map(String));
  const jump = (id: number, target: "source" | "text") => {
    setActive(id);
    root.current?.querySelector(`[data-${target}-citation="${id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  return <CitationContext.Provider value={{ active, jump, validIds }}><div ref={root}>{children}</div></CitationContext.Provider>;
}

export const useCitation = () => useContext(CitationContext);

function CitationTag({ id }: { id: number }) {
  const { active, jump } = useCitation();
  return <button type="button" data-text-citation={id} aria-label={`查看参考来源 ${id}`}
    onClick={() => jump(id, "source")}
    className={`mx-0.5 align-super text-[10px] font-medium text-primary ${active === id ? "rounded bg-primary-soft ring-1 ring-primary" : ""}`}>
    [{id}]
  </button>;
}

export function citeText(text: string, validIds?: ReadonlySet<string>): ReactNode[] {
  return text.split(/(\[\d+\])/g).map((part, index) => /^\[\d+\]$/.test(part)
    && (!validIds || isKnownCitation(part.slice(1, -1), validIds))
      ? <CitationTag key={index} id={Number(part.slice(1, -1))} /> : part);
}

"use client";

import { KnowledgeClientError } from "@/clients/knowledge";
import { KnowledgeSearchError } from "../components/search-states";

export function ConferenceError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return <KnowledgeSearchError error={error instanceof KnowledgeClientError ? error : new KnowledgeClientError("UNKNOWN", "会议数据加载失败")} onRetry={onRetry} />;
}

export function ConferenceEmpty({ children }: { children: React.ReactNode }) {
  return <p role="status" className="rounded-2xl border border-dashed border-line bg-card px-6 py-16 text-center text-sm text-muted">{children}</p>;
}

export function ConferenceSkeleton({ compact = false }: { compact?: boolean }) {
  if (compact) return <div aria-busy="true" aria-label="正在加载会议" className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
    <div className="min-h-40 animate-pulse rounded-xl bg-chip" />
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {Array.from({ length: 6 }, (_, index) => <div key={index} className="h-20 animate-pulse rounded-xl bg-chip" />)}
    </div>
  </div>;
  return <div aria-busy="true" aria-label="正在加载会议" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
    {Array.from({ length: 6 }, (_, index) => <div key={index} className="h-36 animate-pulse rounded-2xl bg-chip" />)}
  </div>;
}

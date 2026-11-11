"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { DiscoveryPaperDto } from "@/clients/backend/discovery";
import { Button } from "@/components/ui/button";
import { PaperCardLayout } from "@/features/knowledge/papers/components/paper-card-layout";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { paperHref } from "@/lib/navigation/paper";
import { fetchDiscoveryFeedPage, mapDiscoveryPaper } from "@/features/search/services/discovery-feed";
import { ScholarError, ScholarLoading } from "./profile-parts";

const batchSize = 5;
const total = 10;

async function loadFeaturedPapers() {
  try {
    const { items } = await fetchDiscoveryFeedPage(null);
    const unique = [...new Map(items.filter((paper) => paper.thumbnailUrl).map((paper) => [paper.id, paper])).values()];
    if (unique.length >= total) {
      return { papers: unique.slice(0, total), fromLibrary: true };
    }
  } catch {
    // The local layout preview can still render the shared card with sample data.
  }

  const response = await fetch("/images/scholar-preview/featured-papers.json");
  if (!response.ok) throw new Error("Featured papers preview is unavailable.");
  const papers: DiscoveryPaperDto[] = await response.json();
  return { papers: papers.map(mapDiscoveryPaper), fromLibrary: false };
}

export function ScholarFeaturedPapers() {
  const [visibleCount, setVisibleCount] = useState(batchSize);
  const returnTo = useCurrentInternalPath();
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["scholars-v2", "preview-featured-papers"],
    queryFn: loadFeaturedPapers,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  return (
    <section className="py-8" aria-labelledby="featured-papers-title">
      <h2 id="featured-papers-title" className="text-lg font-semibold text-ink">论文库精选</h2>
      <p className="mt-1 text-sm text-muted">
        {data && !data.fromLibrary ? "首页论文快照 · " : ""}所有学者页共用的预览论文，与该学者的作者关系无关。
      </p>
      {isPending ? <div className="mt-5"><ScholarLoading /></div> : null}
      {isError ? <div className="mt-5"><ScholarError onRetry={() => void refetch()} /></div> : null}
      {data ? (
        <>
          <div className="mt-5 grid gap-4">
            {data.papers.slice(0, visibleCount).map((paper, index) => (
              <PaperCardLayout
                key={paper.id}
                paper={paper}
                index={index}
                detailHref={data.fromLibrary ? paperHref(paper.id, { mode: "create", source: returnTo }) : undefined}
                behaviorSource="discovery"
                actions={null}
              />
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-center gap-3">
            <p aria-live="polite" className="text-sm tabular-nums text-muted">
              已展示 {Math.min(visibleCount, data.papers.length)} / {data.papers.length} 篇
            </p>
            {visibleCount < data.papers.length ? (
              <Button variant="outline" onClick={() => setVisibleCount((count) => count + batchSize)}>加载更多</Button>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

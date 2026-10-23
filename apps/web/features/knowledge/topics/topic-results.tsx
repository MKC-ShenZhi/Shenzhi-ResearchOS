"use client";

import { useState } from "react";
import type { KnowledgeTopic } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { TopicGrid } from "./topic-grid";
import { groupTopics } from "./topic-url-state";

const PAGE_SIZE = 24;

/** Paginate the full filtered result set, rather than each category separately. */
export function TopicResults({ topics, returnTo }: { topics: KnowledgeTopic[]; returnTo: string }) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const displayedTopics = topics.slice(0, visibleCount);
  const totals = new Map(groupTopics(topics).map(([category, items]) => [category, items.length]));

  return (
    <div className="space-y-10">
      {groupTopics(displayedTopics).map(([category, items]) => (
        <section key={category}>
          <div className="mb-3 flex items-center justify-between gap-4">
            <h2 className="text-2xl font-semibold tracking-tight text-ink">{category}</h2>
            <span className="text-sm text-muted">{totals.get(category)} 个主题</span>
          </div>
          <TopicGrid topics={items} returnTo={returnTo} />
        </section>
      ))}
      <div className="flex flex-col items-center gap-3">
        <p role="status" className="text-sm text-muted">已显示 {displayedTopics.length} / {topics.length} 个主题</p>
        {displayedTopics.length < topics.length ? (
          <Button type="button" variant="outline" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>加载更多主题</Button>
        ) : null}
      </div>
    </div>
  );
}

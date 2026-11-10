"use client";

import type { KnowledgeTopicCategory } from "@/clients/knowledge";

export function TopicCategoryTabs({ categories, total, value, onChange }: {
  categories: KnowledgeTopicCategory[];
  total: number | undefined;
  value: string;
  onChange: (value: string) => void;
}) {
  const tabs = [{ id: "", name: "全部", total }, ...categories];

  return (
    <div className="flex w-full max-w-full justify-start gap-2 overflow-x-auto pb-1" role="tablist" aria-label="主题分类">
      {tabs.map(({ id, name, total }) => {
        const selected = value === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(id)}
            className={`shrink-0 rounded-full border px-4 py-2 text-sm font-medium transition ${selected ? "border-primary/20 bg-primary text-primary-foreground shadow-sm" : "border-line bg-card text-muted hover:border-primary/30 hover:text-ink"}`}
          >
            {name}{total !== undefined && <span className="ml-1.5 tabular-nums opacity-75">{total}</span>}
          </button>
        );
      })}
    </div>
  );
}

"use client";

import type { KnowledgeTopicCategory } from "@/clients/knowledge";

export function TopicCategoryTabs({ categories, value, onChange }: {
  categories: KnowledgeTopicCategory[];
  value: string;
  onChange: (value: string) => void;
}) {
  const tabs = [{ id: "", name: "全部" }, ...categories];

  return (
    <div className="flex w-full flex-wrap gap-1.5" role="tablist" aria-label="主题分类">
      {tabs.map(({ id, name }) => {
        const selected = value === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(id)}
            className={`max-w-full wrap-break-word rounded-full border px-2.5 py-1 text-xs font-medium transition ${selected ? "border-primary/20 bg-primary text-primary-foreground shadow-sm" : "border-line bg-card text-muted hover:border-primary/30 hover:text-ink"}`}
          >
            {name}
          </button>
        );
      })}
    </div>
  );
}

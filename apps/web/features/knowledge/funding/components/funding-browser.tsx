"use client";

import { useMemo, useState } from "react";
import { FundingPanel } from "./funding-panel";
import { FundingTable } from "./funding-table";
import { useDebounce } from "@/hooks/use-debounce";
import { fundings } from "@/features/knowledge/data-funding";

/** 基金库容器 —— 持有搜索/类别状态 */
export function FundingBrowser() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const debouncedQuery = useDebounce(query, 300);

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of fundings) counts.set(f.category, (counts.get(f.category) ?? 0) + 1);
    return [...counts.entries()].map(([name, count]) => ({ name, count }));
  }, []);

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase();
    let list = fundings;
    if (category) list = list.filter((f) => f.category === category);
    if (status) list = list.filter((f) => f.status === status);
    if (q) {
      list = list.filter((f) =>
        [f.title, f.grantNo, f.pi, f.institution]
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    return list;
  }, [debouncedQuery, category, status]);

  return (
    <>
      <FundingPanel
        categories={categories}
        activeCategory={category}
        onCategoryChange={setCategory}
        activeStatus={status}
        onStatusChange={setStatus}
      />
      <FundingTable
        items={filtered}
        totalCount={fundings.length}
        query={query}
        onQueryChange={setQuery}
      />
    </>
  );
}

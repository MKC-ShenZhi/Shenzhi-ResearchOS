"use client";

import { useMemo, useState } from "react";
import { PatentPanel } from "./patent-panel";
import { PatentTable, type PatentSort } from "./patent-table";
import { useDebounce } from "@/hooks/use-debounce";
import { patents } from "@/features/knowledge/data-patents";

/** 专利库容器 —— 持有搜索/领域/排序状态,领域筛选与搜索可叠加 */
export function PatentsBrowser() {
  const [query, setQuery] = useState("");
  const [field, setField] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [sort, setSort] = useState<PatentSort>("latest");
  const debouncedQuery = useDebounce(query, 300);

  const fields = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of patents) counts.set(p.field, (counts.get(p.field) ?? 0) + 1);
    return [...counts.entries()].map(([name, count]) => ({ name, count }));
  }, []);

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase();
    let list = patents;
    if (field) list = list.filter((p) => p.field === field);
    if (status) list = list.filter((p) => p.status === status);
    if (q) {
      list = list.filter((p) =>
        [p.title, p.applicationNo, p.applicant]
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    return [...list].sort((a, b) =>
      sort === "latest"
        ? b.publishedAt.localeCompare(a.publishedAt)
        : b.citations - a.citations,
    );
  }, [debouncedQuery, field, sort, status]);

  return (
    <>
      <PatentPanel fields={fields} activeField={field} onFieldChange={setField} activeStatus={status} onStatusChange={setStatus} />
      <PatentTable
        items={filtered}
        totalCount={patents.length}
        query={query}
        onQueryChange={setQuery}
        sort={sort}
        onSortChange={setSort}
      />
    </>
  );
}

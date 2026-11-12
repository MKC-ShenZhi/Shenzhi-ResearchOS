"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { searchNsfcProjects } from "@/clients/knowledge/nsfc-projects";
import { nsfcDirectoryHref } from "./navigation";

const pageSize = 20;

export function NsfcProjectDirectory() {
  const router = useRouter();
  const params = useSearchParams();
  const query = (params.get("projectQuery") ?? "").slice(0, 200).trim();
  const requestedPage = Number(params.get("page") ?? 1);
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 && requestedPage <= 100_000
    ? requestedPage : 1;
  const offset = (page - 1) * pageSize;
  const detailParams = new URLSearchParams();
  if (query) detailParams.set("q", query);
  if (page > 1) detailParams.set("page", String(page));
  const detailQuery = detailParams.size ? `?${detailParams}` : "";
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["knowledge", "nsfc-projects", query, page],
    queryFn: ({ signal }) => searchNsfcProjects(query, pageSize, offset, signal),
    retry: false,
  });

  return (
    <div className="space-y-5">
      <form
        role="search"
        key={query}
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const value = String(new FormData(event.currentTarget).get("q") ?? "").trim();
          router.push(nsfcDirectoryHref(value));
        }}
      >
        <input
          type="search"
          name="q"
          aria-label="搜索国自然项目"
          placeholder="批准号、项目名、主题、负责人或机构"
          defaultValue={query}
          maxLength={200}
          className="min-w-0 flex-1 rounded-lg border border-line bg-background px-4 py-2.5 text-sm text-ink"
        />
        <button className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
          <Search size={16} aria-hidden="true" /> 搜索
        </button>
      </form>
      {isPending && <p role="status" className="text-sm text-muted">正在加载项目…</p>}
      {isError && (
        <p role="alert" className="text-sm text-muted">
          项目加载失败。 <button onClick={() => void refetch()} className="text-primary underline">重试</button>
        </p>
      )}
      {data && (
        <section aria-label="项目结果" className="space-y-3">
          <p className="text-sm text-muted">
            {data.total} 个项目{data.snapshot ? " · 国自然结项样本" : ""}
          </p>
          {data.items.length === 0 && (
            <p className="rounded-xl border border-line p-5 text-sm text-muted">
              {data.total ? "本页没有项目。" : "没有找到匹配的项目。"}{" "}
              <Link href={nsfcDirectoryHref(data.total ? query : "")} className="text-primary underline">
                {data.total ? "返回第一页" : "查看全部"}
              </Link>
            </p>
          )}
          <ul className="divide-y divide-line rounded-xl border border-line bg-card">
            {data.items.map((project) => (
              <li key={project.awardNumber}>
                <Link
                  href={`/knowledge/nsfc-projects/${encodeURIComponent(project.awardNumber)}${detailQuery}`}
                  className="group flex items-center justify-between gap-4 px-5 py-4 hover:bg-primary-soft"
                >
                  <div className="min-w-0">
                    <p className="mb-1 text-xs text-muted">{[project.awardNumber, project.program, project.awardYear].filter(Boolean).join(" · ")}</p>
                    <h2 className="font-semibold text-ink group-hover:text-primary">{project.name}</h2>
                    <p className="mt-1 text-sm text-muted">{project.institutions.join("、")}</p>
                  </div>
                  <ArrowRight size={18} className="shrink-0 text-muted group-hover:text-primary" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
          {data.items.length > 0 && data.total > pageSize && (
            <nav aria-label="项目分页" className="flex items-center gap-5 text-sm">
              {page > 1 && <Link className="text-primary" href={nsfcDirectoryHref(query, page - 1)}>上一页</Link>}
              <span className="text-muted">第 {page} / {Math.ceil(data.total / pageSize)} 页</span>
              {offset + pageSize < data.total && <Link className="text-primary" href={nsfcDirectoryHref(query, page + 1)}>下一页</Link>}
            </nav>
          )}
        </section>
      )}
    </div>
  );
}

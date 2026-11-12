"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Search, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { searchNsfcProjects, type ProjectSummary } from "@/clients/knowledge/nsfc-projects";
import { nsfcDirectoryHref } from "./navigation";

const pageSize = 20;

function ProjectCard({ project, detailQuery }: { project: ProjectSummary; detailQuery: string }) {
  const metadata = [
    ["批准号", project.awardNumber],
    ["项目类型", project.program || "未收录"],
    ["批准年份", `${project.awardYear} 年`],
  ];
  const facts = [
    ["依托单位", project.institutions.join("、")],
    ["项目负责人", project.principalInvestigators?.join("、")],
    ["项目状态", project.status],
    ["收录论文", project.paperCount == null ? "" : `${project.paperCount} 篇`],
  ];

  return (
    <Link
      href={`/knowledge/nsfc-projects/${encodeURIComponent(project.awardNumber)}${detailQuery}`}
      className="group grid h-full gap-4 rounded-xl border border-line bg-card p-4 transition-colors hover:border-primary/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary sm:p-5 @min-[38rem]:grid-cols-[minmax(0,1fr)_minmax(13rem,0.46fr)] @min-[38rem]:gap-6"
    >
      <div className="min-w-0 space-y-2.5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 break-words text-base font-semibold leading-snug text-ink group-hover:text-primary">
            {project.name}
          </h2>
          <ArrowUpRight size={16} className="mt-0.5 shrink-0 text-faint group-hover:text-primary" aria-hidden="true" />
        </div>
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {metadata.map(([label, value]) => (
            <div key={label} className="flex min-w-0 flex-wrap gap-x-1.5">
              <dt className="text-muted">{label}</dt>
              <dd className="break-words font-medium text-ink-2">{value}</dd>
            </div>
          ))}
        </dl>
        {project.summary && <p className="line-clamp-2 text-sm leading-relaxed text-muted">{project.summary}</p>}
      </div>
      <dl className="grid min-w-0 grid-cols-2 content-start gap-x-4 gap-y-2 border-t border-line pt-3 text-xs @min-[38rem]:grid-cols-1 @min-[38rem]:border-l @min-[38rem]:border-t-0 @min-[38rem]:pl-5 @min-[38rem]:pt-0">
        {facts.map(([label, value]) => value && (
          <div key={label} className="grid min-w-0 gap-0.5 @min-[38rem]:grid-cols-[4rem_minmax(0,1fr)] @min-[38rem]:gap-2">
            <dt className="text-muted">{label}</dt>
            <dd className="break-words font-medium text-ink-2">{value}</dd>
          </div>
        ))}
      </dl>
    </Link>
  );
}

export function NsfcProjectDirectory() {
  const router = useRouter();
  const params = useSearchParams();
  const query = (params.get("projectQuery") ?? "").slice(0, 200).trim();
  const keyword = (params.get("keyword") ?? "").slice(0, 200).trim();
  const requestedPage = Number(params.get("page") ?? 1);
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 && requestedPage <= 100_000
    ? requestedPage : 1;
  const offset = (page - 1) * pageSize;
  const detailParams = new URLSearchParams();
  if (query) detailParams.set("q", query);
  if (keyword) detailParams.set("keyword", keyword);
  if (page > 1) detailParams.set("page", String(page));
  const detailQuery = detailParams.size ? `?${detailParams}` : "";
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["knowledge", "nsfc-projects", query, keyword, page],
    queryFn: ({ signal }) => searchNsfcProjects(query, pageSize, offset, keyword, signal),
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
          router.push(nsfcDirectoryHref(value, 1, keyword));
        }}
      >
        <input
          type="search"
          name="q"
          aria-label="搜索国自然项目"
          placeholder="批准号、项目名、关键词、负责人或机构"
          defaultValue={query}
          maxLength={200}
          className="min-w-0 flex-1 rounded-lg border border-line bg-background px-4 py-2.5 text-sm text-ink"
        />
        <button className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
          <Search size={16} aria-hidden="true" /> 搜索
        </button>
      </form>
      {keyword && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">研究关键词</span>
          <Link
            href={nsfcDirectoryHref(query)}
            aria-label={`移除研究关键词筛选：${keyword}`}
            className="inline-flex max-w-full items-center gap-2 rounded-full bg-primary-soft px-3 py-1.5 text-primary hover:underline"
          >
            <span className="min-w-0 break-words">{keyword}</span>
            <X size={14} className="shrink-0" aria-hidden="true" />
          </Link>
        </div>
      )}
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
              <Link href={data.total ? nsfcDirectoryHref(query, 1, keyword) : nsfcDirectoryHref()} className="text-primary underline">
                {data.total ? "返回第一页" : "查看全部"}
              </Link>
            </p>
          )}
          <ul className="@container space-y-2.5">
            {data.items.map((project) => (
              <li key={project.awardNumber}>
                <ProjectCard project={project} detailQuery={detailQuery} />
              </li>
            ))}
          </ul>
          {data.items.length > 0 && data.total > pageSize && (
            <nav aria-label="项目分页" className="flex items-center gap-5 text-sm">
              {page > 1 && <Link className="text-primary" href={nsfcDirectoryHref(query, page - 1, keyword)}>上一页</Link>}
              <span className="text-muted">第 {page} / {Math.ceil(data.total / pageSize)} 页</span>
              {offset + pageSize < data.total && <Link className="text-primary" href={nsfcDirectoryHref(query, page + 1, keyword)}>下一页</Link>}
            </nav>
          )}
        </section>
      )}
    </div>
  );
}

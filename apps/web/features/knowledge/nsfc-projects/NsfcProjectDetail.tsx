"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { ApiError } from "@/clients/backend/http";
import { getNsfcProject } from "@/clients/knowledge/nsfc-projects";

function SourceLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-primary hover:underline">
      {label} <ExternalLink size={14} aria-hidden="true" />
    </a>
  );
}

export function NsfcProjectDetail({ awardNumber, backHref }: { awardNumber: string; backHref: string }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["knowledge", "nsfc-project", awardNumber],
    queryFn: ({ signal }) => getNsfcProject(awardNumber, signal),
    retry: false,
  });
  const missing = error instanceof ApiError && error.status === 404;

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-8">
      <Link href={backHref} className="inline-flex items-center gap-2 text-sm text-muted hover:text-primary">
        <ArrowLeft size={16} aria-hidden="true" /> 返回国自然项目
      </Link>
      {isPending && <p role="status" className="text-sm text-muted">正在加载项目详情…</p>}
      {error && (
        <p role="alert" className="text-sm text-muted">
          {missing ? "未找到该项目。" : "项目详情加载失败。"}
          {!missing && <button onClick={() => void refetch()} className="ml-2 text-primary underline">重试</button>}
        </p>
      )}
      {data && (
        <article className="space-y-7">
          <header className="space-y-3 border-b border-line pb-6">
            <p className="text-sm text-muted">{[data.awardNumber, data.program, data.status, data.snapshot ? "结项项目样本" : ""].filter(Boolean).join(" · ")}</p>
            <h1 className="text-3xl font-bold leading-tight tracking-tight text-ink">{data.name}</h1>
            <p className="text-sm text-muted">批准年份 {data.awardYear}{data.startDate && data.endDate ? ` · 执行期 ${data.startDate} 至 ${data.endDate}` : ""}</p>
            {data.sourceUrl && <SourceLink href={data.sourceUrl} label="基金委项目详情" />}
          </header>
          <section className="space-y-3">
            <h2 className="text-xl font-semibold text-ink">项目摘要</h2>
            <p className="whitespace-pre-line text-sm leading-7 text-ink">{data.summary || "暂无摘要"}</p>
            {data.topics.length > 0 && (
              <ul aria-label="项目主题" className="flex flex-wrap gap-2">
                {[...new Set(data.topics)].map((topic) => (
                  <li key={topic}>
                    <Link
                      href={`/knowledge/nsfc-projects?${new URLSearchParams({ q: topic })}`}
                      className="inline-block rounded-full border border-line px-3 py-1 text-sm text-ink hover:text-primary"
                    >
                      {topic}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="space-y-4 rounded-xl border border-line p-5">
            <h2 className="text-xl font-semibold text-ink">项目关系</h2>
            <dl className="grid gap-4 sm:grid-cols-3">
              <div><dt className="text-sm text-muted">依托单位</dt><dd className="mt-1 text-ink">{data.institutions.join("、") || "暂无记录"}</dd></div>
              <div><dt className="text-sm text-muted">项目负责人</dt><dd className="mt-1 text-ink">{data.members.filter((member) => member.role === "PI").map((member) => member.name).join("、") || "暂无记录"}</dd></div>
              <div><dt className="text-sm text-muted">参与人员</dt><dd className="mt-1 text-ink">{data.members.filter((member) => member.role !== "PI").map((member) => member.name).join("、") || "暂无记录"}</dd></div>
            </dl>
          </section>
          <section className="space-y-3">
            <h2 className="text-xl font-semibold text-ink">成果论文（{data.papers.length}）</h2>
            {data.papers.length === 0 ? <p className="text-sm text-muted">暂无成果论文记录。</p> : (
              <ul className="divide-y divide-line rounded-xl border border-line">
                {data.papers.map((paper) => (
                  <li key={paper.id} className="px-5 py-3 text-sm text-ink">
                    {paper.sourceUrl ? <SourceLink href={paper.sourceUrl} label={paper.title} /> : paper.title}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </article>
      )}
    </main>
  );
}

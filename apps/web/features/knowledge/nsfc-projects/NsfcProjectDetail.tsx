"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { ApiError } from "@/clients/backend/http";
import { getNsfcProject } from "@/clients/knowledge/nsfc-projects";
import { nsfcDirectoryHref } from "./navigation";

function SourceLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-primary hover:underline">
      {label} <ExternalLink size={14} aria-hidden="true" />
    </a>
  );
}

function ParticipantNames({ names }: { names: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const namesId = useId();
  const previewLimit = 3;
  const remaining = names.length - previewLimit;
  const visibleNames = expanded ? names : names.slice(0, previewLimit);

  return (
    <>
      <span id={namesId}>{visibleNames.join("、") || "暂无"}</span>
      {remaining > 0 && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={namesId}
          aria-label={expanded ? "收起参与人员" : `展开其余 ${remaining} 位参与人员`}
          className="ml-1 inline-flex min-h-7 items-center rounded-md px-1.5 text-sm font-medium text-primary hover:bg-primary-soft focus-visible:outline-2 focus-visible:outline-primary"
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? "收起" : "…"}
        </button>
      )}
    </>
  );
}

export function NsfcProjectDetail({ awardNumber, backHref }: { awardNumber: string; backHref: string }) {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["knowledge", "project", awardNumber],
    queryFn: ({ signal }) => getNsfcProject(awardNumber, signal),
    retry: false,
  });
  const missing = error instanceof ApiError && error.status === 404;
  const leads = data?.members.filter((member) => member.role === "PI").map((member) => member.name) ?? [];
  const participants = data?.members.filter((member) => member.role !== "PI").map((member) => member.name) ?? [];

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-8">
      <Link href={backHref} className="inline-flex items-center gap-2 text-sm text-muted hover:text-primary">
        <ArrowLeft size={16} aria-hidden="true" /> 返回项目基金库
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
          <header className="space-y-4">
            <h1 className="text-3xl font-bold leading-tight tracking-tight text-ink">{data.name}</h1>
            <div className="rounded-xl border border-line bg-card p-4 text-sm sm:p-5">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <dt className="text-xs text-muted">批准号</dt>
                  <dd className="mt-1.5 font-medium tabular-nums text-ink">{data.awardNumber}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">项目类型</dt>
                  <dd className="mt-1.5 font-medium text-ink">{data.program || "未收录"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">批准年份</dt>
                  <dd className="mt-1.5 font-medium text-ink">{data.awardYear} 年</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">项目状态</dt>
                  <dd className="mt-1">
                    <span className="inline-block rounded-full bg-primary-soft px-2.5 py-0.5 font-medium text-primary">
                      {data.status || "未收录"}
                    </span>
                  </dd>
                </div>
              </dl>
              <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4 md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.5fr)]">
                <div>
                  <dt className="text-xs text-muted">项目执行期</dt>
                  <dd className="mt-1.5 font-medium tabular-nums text-ink">
                    {data.startDate && data.endDate ? `${data.startDate} 至 ${data.endDate}` : "暂无"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">依托单位</dt>
                  <dd className="mt-1.5 break-words font-medium text-ink">{data.institutions.join("、") || "暂无"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">项目负责人</dt>
                  <dd className="mt-1.5 break-words font-medium text-ink">{leads.join("、") || "暂无"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">参与人员</dt>
                  <dd className="mt-1.5 break-words text-ink">
                    <ParticipantNames key={data.awardNumber} names={participants} />
                  </dd>
                </div>
              </dl>
            </div>
            {data.sourceUrl && <SourceLink href={data.sourceUrl} label="基金委项目详情" />}
          </header>
          <section className="space-y-3">
            <h2 className="text-xl font-semibold text-ink">项目摘要</h2>
            <p className="whitespace-pre-line text-sm leading-7 text-ink">{data.summary || "暂无摘要"}</p>
            {data.topics.length > 0 && (
              <div className="space-y-2 pt-2">
                <h3 id="nsfc-keywords" className="text-sm font-medium text-ink">研究关键词</h3>
                <ul aria-labelledby="nsfc-keywords" className="flex flex-wrap gap-2">
                  {[...new Set(data.topics)].map((topic) => (
                    <li key={topic} className="min-w-0">
                      <Link
                        href={nsfcDirectoryHref("", topic)}
                        aria-label={`按研究关键词筛选：${topic}`}
                        className="inline-block break-words rounded-full border border-primary/20 bg-primary-soft px-3 py-1 text-sm text-primary hover:border-primary/50 hover:underline"
                      >
                        {topic}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
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

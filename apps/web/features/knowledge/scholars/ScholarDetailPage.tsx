"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, FileText, RotateCw, UserRound } from "lucide-react";
import { getKnowledgeClient, KnowledgeClientError } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { paperHref } from "@/lib/navigation/paper";
import { scholarHref } from "@/lib/navigation/scholar";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";

function TagSection({ title, values }: { title: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <section className="rounded-2xl bg-card p-5 shadow-card">
      <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {values.map((value, index) => (
          <span key={`${value}-${index}`} className="rounded-lg bg-chip px-3 py-1.5 text-xs text-muted">
            {value}
          </span>
        ))}
      </div>
    </section>
  );
}

export function ScholarDetailPage({ scholarId }: { scholarId: string }) {
  const returnTo = usePathname();
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["knowledge", "scholars", scholarId],
    queryFn: () => getKnowledgeClient().scholar(scholarId),
    retry: knowledgeQueryRetry,
  });

  if (isPending) {
    return (
      <div className="mx-auto max-w-[1040px] space-y-5 px-6 py-8 lg:px-8" aria-busy="true">
        <div className="h-9 w-32 animate-pulse rounded-lg bg-chip" />
        <div className="h-40 animate-pulse rounded-2xl bg-card shadow-card" />
        <div className="grid gap-5 md:grid-cols-2">
          <div className="h-64 animate-pulse rounded-2xl bg-card shadow-card" />
          <div className="h-64 animate-pulse rounded-2xl bg-card shadow-card" />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    const knowledgeError = error instanceof KnowledgeClientError
      ? error
      : new KnowledgeClientError("UNKNOWN", "学者详情加载失败");
    return (
      <div className="mx-auto flex min-h-[520px] max-w-[1040px] flex-col items-center justify-center px-6 text-center">
        <p className="text-base font-semibold text-ink">无法加载学者详情</p>
        <p className="mt-2 max-w-md text-sm text-muted">{knowledgeError.message}</p>
        <div className="mt-5 flex gap-3">
          <Link href="/knowledge/scholars">
            <Button variant="outline"><ArrowLeft />返回学者库</Button>
          </Link>
          <Button onClick={() => void refetch()}><RotateCw />重试</Button>
        </div>
      </div>
    );
  }

  const years = [...new Set(data.years)].sort((a, b) => b - a).map(String);

  return (
    <div className="mx-auto max-w-[1040px] space-y-5 px-6 py-8 lg:px-8">
      <Link href="/knowledge/scholars" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-primary">
        <ArrowLeft className="size-4" />
        返回学者库
      </Link>

      <header className="flex flex-wrap items-center gap-5 rounded-2xl bg-card p-6 shadow-card">
        <span className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-primary-soft text-primary">
          <UserRound className="size-7" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-ink">{data.name}</h1>
          <p className="mt-1.5 text-sm text-muted">知识底座收录论文 {data.paperCount} 篇</p>
        </div>
      </header>

      <div className="grid items-start gap-5 md:grid-cols-2">
        <div className="space-y-5">
          <TagSection title="发表年份" values={years} />
          <TagSection title="会议" values={data.conferences} />
          <TagSection title="研究主题" values={data.topics} />
          <TagSection title="机构" values={data.institutions} />
          <TagSection title="基金信息" values={data.funding} />
        </div>

        <div className="space-y-5">
          {data.papers.length > 0 && (
            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h2 className="text-[15px] font-semibold text-ink">论文成果</h2>
              <div className="mt-3 divide-y divide-line">
                {data.papers.map((paper) => (
                  <Link
                    key={paper.id}
                    href={paperHref(paper.id, { mode: "create", source: returnTo })}
                    className="group flex items-start gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <FileText className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium leading-snug text-ink group-hover:text-primary">
                        {paper.title}
                      </span>
                      {paper.year !== null && (
                        <span className="mt-1 block text-xs text-faint">{paper.year}</span>
                      )}
                    </span>
                    <ArrowRight className="mt-0.5 size-4 shrink-0 text-faint group-hover:text-primary" />
                  </Link>
                ))}
              </div>
            </section>
          )}

          {data.coauthors.length > 0 && (
            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h2 className="text-[15px] font-semibold text-ink">合作学者</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {data.coauthors.map((coauthor) => (
                  <Link
                    key={coauthor.id}
                    href={scholarHref(coauthor.id)}
                    className="rounded-lg bg-panel px-3 py-2 text-sm text-ink-2 hover:bg-primary-soft hover:text-primary"
                  >
                    {coauthor.name}
                  </Link>
                ))}
              </div>
            </section>
          )}

          {data.papers.length === 0 && data.coauthors.length === 0 && (
            <div className="rounded-2xl bg-card p-8 text-center text-sm text-muted shadow-card">
              暂无论文或合作学者信息
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

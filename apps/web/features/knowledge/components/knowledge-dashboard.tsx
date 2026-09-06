"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type ComponentType } from "react";
import {
  ArrowRight,
  Award,
  Banknote,
  BookOpen,
  Building2,
  Clock3,
  FileText,
  FolderOpen,
  Network,
  Search,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import { libraryFolders, libraryItems, libraryTags } from "@/lib/data/library";
import { patents } from "@/lib/data/patents";
import { fundings } from "@/lib/data/funding";
import { scholars } from "@/lib/data/scholars";
import { institutions } from "@/lib/data/institutions";
import { cn } from "@/lib/utils";

type SearchType = "全部" | "论文" | "专利" | "基金" | "学者" | "机构";

interface SearchEntry {
  type: Exclude<SearchType, "全部">;
  title: string;
  meta: string;
  href: string;
}

const searchTypes: SearchType[] = ["全部", "论文", "专利", "基金", "学者", "机构"];

const typeStyle: Record<Exclude<SearchType, "全部">, string> = {
  论文: "bg-primary-soft text-primary",
  专利: "bg-brand-violet/10 text-brand-violet",
  基金: "bg-brand-gold/20 text-ink",
  学者: "bg-success-soft text-success",
  机构: "bg-brand-cyan/10 text-brand-cyan",
};

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line/70 bg-panel px-4 py-3">
      <p className="text-lg font-bold tracking-tight text-ink">{value}</p>
      <p className="mt-0.5 truncate text-[11px] text-faint">{label}</p>
    </div>
  );
}

function CardHeader({
  icon: Icon,
  title,
  description,
  href,
  tone = "primary",
}: {
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  title: string;
  description: string;
  href: string;
  tone?: "primary" | "violet" | "gold" | "cyan" | "green";
}) {
  const tones = {
    primary: "bg-primary-soft text-primary",
    violet: "bg-brand-violet/10 text-brand-violet",
    gold: "bg-brand-gold/20 text-ink",
    cyan: "bg-brand-cyan/10 text-brand-cyan",
    green: "bg-success-soft text-success",
  };

  return (
    <div className="flex items-start gap-3">
      <span className={cn("flex size-11 shrink-0 items-center justify-center rounded-xl", tones[tone])}>
        <Icon className="size-5" strokeWidth={1.8} />
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="text-[15px] font-bold text-ink">
          <Link href={href} onClick={(event) => event.stopPropagation()} className="hover:text-primary">
            {title}
          </Link>
        </h2>
        <p className="mt-0.5 text-xs leading-relaxed text-muted">{description}</p>
      </div>
      <Link
        href={href}
        aria-label={`进入${title}`}
        className="flex size-8 shrink-0 items-center justify-center rounded-lg text-faint transition-colors hover:bg-chip hover:text-primary"
      >
        <ArrowRight className="size-4" />
      </Link>
    </div>
  );
}

function MiniNetwork({ institution = false }: { institution?: boolean }) {
  const nodes = institution
    ? [
        [18, 48, 7], [45, 22, 5], [53, 54, 9], [78, 29, 6], [83, 66, 5],
      ]
    : [
        [16, 35, 5], [39, 18, 6], [51, 48, 9], [76, 25, 5], [82, 63, 6], [31, 69, 4],
      ];
  const lines = institution
    ? [[18,48,45,22],[18,48,53,54],[45,22,78,29],[53,54,78,29],[53,54,83,66]]
    : [[16,35,39,18],[16,35,51,48],[39,18,51,48],[51,48,76,25],[51,48,82,63],[51,48,31,69]];

  return (
    <svg viewBox="0 0 100 82" className="h-24 w-full" aria-hidden>
      {lines.map((line, index) => (
        <line key={index} x1={line[0]} y1={line[1]} x2={line[2]} y2={line[3]} className="stroke-primary/20" strokeWidth="1.2" />
      ))}
      {nodes.map(([x, y, r], index) => (
        <circle
          key={index}
          cx={x}
          cy={y}
          r={r}
          className={index === 2 ? "fill-primary" : institution ? "fill-brand-cyan/55" : "fill-primary/35"}
        />
      ))}
    </svg>
  );
}

export function KnowledgeDashboard() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeType, setActiveType] = useState<SearchType>("全部");

  const entries = useMemo<SearchEntry[]>(() => [
    ...libraryItems.map((item) => ({
      type: "论文" as const,
      title: item.title,
      meta: `${item.venue} · ${item.authors}`,
      href: `/papers/${encodeURIComponent(item.id)}`,
    })),
    ...patents.map((item) => ({
      type: "专利" as const,
      title: item.title,
      meta: `${item.applicant} · ${item.status}`,
      href: "/knowledge/patents",
    })),
    ...fundings.map((item) => ({
      type: "基金" as const,
      title: item.title,
      meta: `${item.institution} · ${item.amount}`,
      href: "/knowledge/funding",
    })),
    ...scholars.map((item) => ({
      type: "学者" as const,
      title: `${item.nameCn} · ${item.nameEn}`,
      meta: `${item.affiliation} · h-index ${item.hIndex}`,
      href: `/scholars/${item.id}`,
    })),
    ...institutions.map((item) => ({
      type: "机构" as const,
      title: item.nameCn,
      meta: `${item.type} · ${item.location}`,
      href: "/knowledge/institutions",
    })),
  ], []);

  const results = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return [];
    return entries
      .filter((entry) => activeType === "全部" || entry.type === activeType)
      .filter((entry) => `${entry.title} ${entry.meta}`.toLowerCase().includes(keyword))
      .slice(0, 6);
  }, [activeType, entries, query]);

  const openCard = (href: string) => router.push(href);
  const cardKeyDown = (event: React.KeyboardEvent<HTMLElement>, href: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      router.push(href);
    }
  };

  return (
    <div className="mx-auto max-w-[1180px] px-6 py-7 lg:px-8 lg:py-9">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-ink">知识库</h1>
            <span className="rounded-full bg-primary-soft px-2.5 py-1 text-[11px] font-medium text-primary">科研资产中心</span>
          </div>
          <p className="mt-1.5 text-sm text-muted">连接论文、专利、基金、学者与机构，让知识不再彼此孤立</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Link
            href="/knowledge/search"
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-3.5 text-xs font-medium text-primary-foreground shadow-card transition-colors hover:bg-primary-deep"
          >
            <Search className="size-4" />
            论文检索
          </Link>
          <Link href="/knowledge/graph" className="flex h-9 items-center gap-2 rounded-lg border border-line bg-card px-3.5 text-xs font-medium text-ink-2 shadow-card transition-colors hover:bg-chip hover:text-primary">
            <Network className="size-4" />
            打开私域知识图谱
          </Link>
        </div>
      </header>

      <section className="relative mt-6 rounded-2xl bg-card p-4 shadow-card">
        <div className="flex items-center gap-3 rounded-xl border border-line bg-panel px-4">
          <Search className="size-5 shrink-0 text-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索论文、专利、基金、学者或研究机构…"
            className="h-12 min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-faint"
          />
          <span className="hidden items-center gap-1 text-[11px] text-faint sm:flex">
            <Sparkles className="size-3.5" /> 跨库检索
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {searchTypes.map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setActiveType(type)}
              className={cn(
                "h-7 rounded-full px-3 text-xs transition-colors",
                activeType === type ? "bg-primary text-white" : "bg-chip text-muted hover:text-ink",
              )}
            >
              {type}
            </button>
          ))}
        </div>

        {query.trim() && (
          <div className="absolute inset-x-4 top-[82px] z-20 overflow-hidden rounded-xl border border-line bg-card shadow-pop">
            {results.length ? (
              <div className="divide-y divide-line">
                {results.map((result, index) => (
                  <Link key={`${result.type}-${result.title}-${index}`} href={result.href} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-panel">
                    <span className={cn("rounded-md px-2 py-1 text-[10px] font-medium", typeStyle[result.type])}>{result.type}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{result.title}</p>
                      <p className="mt-0.5 truncate text-xs text-faint">{result.meta}</p>
                    </div>
                    <ArrowRight className="size-4 shrink-0 text-faint" />
                  </Link>
                ))}
              </div>
            ) : (
              <div className="px-4 py-6 text-center text-sm text-muted">没有找到相关科研资产，试试更短的关键词</div>
            )}
          </div>
        )}
      </section>

      <section className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Metric value="93" label="文献资产" />
        <Metric value={String(patents.length)} label="专利记录" />
        <Metric value={String(fundings.length)} label="基金项目" />
        <Metric value={String(scholars.length)} label="关注学者" />
        <Metric value={String(institutions.length)} label="研究机构" />
      </section>

      <section className="mt-5 grid gap-5 xl:grid-cols-12">
        <article
          role="link"
          tabIndex={0}
          onClick={() => openCard("/knowledge/papers")}
          onKeyDown={(event) => cardKeyDown(event, "/knowledge/papers")}
          className="group overflow-hidden rounded-2xl bg-card p-6 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-2 focus-visible:outline-primary xl:col-span-7 xl:row-span-2"
        >
          <CardHeader icon={BookOpen} title="论文库" description="管理私有论文与收藏文献，按文件夹、标签和研究主题组织" href="/knowledge/papers" />
          <div className="mt-5 grid gap-5 lg:grid-cols-[180px_1fr]">
            <div className="rounded-xl bg-panel p-4">
              <p className="flex items-center gap-2 text-xs font-semibold text-ink-2"><FolderOpen className="size-4 text-primary" />文献文件夹</p>
              <ul className="mt-3 space-y-1.5">
                {libraryFolders.slice(0, 4).map((folder) => (
                  <li key={folder.name} className={cn("flex items-center justify-between rounded-lg px-2.5 py-2 text-xs", folder.active ? "bg-primary-soft font-medium text-primary" : "text-muted")}>
                    <span>{folder.name}</span><span>{folder.count}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="min-w-0">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-ink-2">最近加入</p>
                <span className="text-[11px] text-faint">共 93 篇</span>
              </div>
              <div className="mt-2 divide-y divide-line">
                {libraryItems.map((item) => (
                  <Link key={item.id} href={`/papers/${encodeURIComponent(item.id)}`} onClick={(event) => event.stopPropagation()} className="group/item flex items-start gap-3 py-3 first:pt-1">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><FileText className="size-4" /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-ink group-hover/item:text-primary">{item.title}</span>
                      <span className="mt-1 block truncate text-[11px] text-faint">{item.venue} · {item.authors}</span>
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
            {libraryTags.map((tag) => <span key={tag} className="rounded-full bg-chip px-3 py-1 text-[11px] text-muted">#{tag}</span>)}
          </div>
        </article>

        <article role="link" tabIndex={0} onClick={() => openCard("/knowledge/patents")} onKeyDown={(event) => cardKeyDown(event, "/knowledge/patents")} className="rounded-2xl bg-card p-5 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-2 focus-visible:outline-primary xl:col-span-5">
          <CardHeader icon={Award} title="专利库" description="按技术领域与法律状态追踪创新成果" href="/knowledge/patents" tone="violet" />
          <div className="mt-4 grid grid-cols-3 gap-2">
            <Metric value="4" label="已授权" /><Metric value="3" label="审查中" /><Metric value="5" label="技术领域" />
          </div>
          <p className="mt-4 truncate text-xs text-muted"><span className="font-medium text-ink-2">最新：</span>{patents[0]?.title}</p>
        </article>

        <article role="link" tabIndex={0} onClick={() => openCard("/knowledge/funding")} onKeyDown={(event) => cardKeyDown(event, "/knowledge/funding")} className="rounded-2xl bg-card p-5 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-2 focus-visible:outline-primary xl:col-span-5">
          <CardHeader icon={Banknote} title="项目基金库" description="洞察资助方向、项目金额与研究进展" href="/knowledge/funding" tone="gold" />
          <div className="mt-4 flex items-end gap-2">
            {[42, 66, 52, 84, 72, 94].map((height, index) => (
              <div key={index} className="flex-1 rounded-t-md bg-primary/15" style={{ height }}><div className="w-full rounded-t-md bg-primary" style={{ height: `${Math.max(10, height - 36)}px` }} /></div>
            ))}
            <div className="ml-2 shrink-0 pb-1 text-right"><p className="text-xl font-bold text-ink">10</p><p className="text-[11px] text-faint">项目在库</p></div>
          </div>
        </article>

        <article role="link" tabIndex={0} onClick={() => openCard("/knowledge/scholars")} onKeyDown={(event) => cardKeyDown(event, "/knowledge/scholars")} className="rounded-2xl bg-card p-5 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-2 focus-visible:outline-primary xl:col-span-5">
          <CardHeader icon={Users} title="学者关系" description="从合作网络与引用脉络中发现关键学者" href="/knowledge/scholars" tone="green" />
          <div className="mt-2 grid grid-cols-[1fr_120px] items-center gap-3">
            <div className="space-y-2">
              {scholars.slice(0, 3).map((scholar) => (
                <Link key={scholar.id} href={`/scholars/${scholar.id}`} onClick={(event) => event.stopPropagation()} className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-panel">
                  <span className="flex size-7 items-center justify-center rounded-full text-[10px] font-semibold text-white" style={{ backgroundColor: scholar.avatarColor }}>{scholar.initials}</span>
                  <span className="min-w-0"><span className="block truncate text-xs font-medium text-ink">{scholar.nameCn}</span><span className="block text-[10px] text-faint">h-index {scholar.hIndex}</span></span>
                </Link>
              ))}
            </div>
            <MiniNetwork />
          </div>
        </article>

        <article role="link" tabIndex={0} onClick={() => openCard("/knowledge/institutions")} onKeyDown={(event) => cardKeyDown(event, "/knowledge/institutions")} className="rounded-2xl bg-card p-5 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-2 focus-visible:outline-primary xl:col-span-7">
          <CardHeader icon={Building2} title="研究机构" description="浏览高校、研究院与企业实验室的科研画像和优势方向" href="/knowledge/institutions" tone="cyan" />
          <div className="mt-3 grid items-stretch gap-4 sm:grid-cols-[1fr_190px]">
            <div className="grid grid-cols-2 gap-2">
              {institutions.slice(0, 4).map((institution) => (
                <Link key={institution.id} href="/knowledge/institutions" onClick={(event) => event.stopPropagation()} className="flex items-center gap-2 rounded-xl bg-panel p-2.5 hover:bg-chip">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg text-[9px] font-bold text-white" style={{ backgroundColor: institution.logoColor }}>{institution.initials}</span>
                  <span className="min-w-0"><span className="block truncate text-xs font-medium text-ink">{institution.nameCn}</span><span className="block truncate text-[10px] text-faint">{institution.type} · {institution.location}</span></span>
                </Link>
              ))}
            </div>
            <div className="rounded-xl bg-panel p-3.5">
              <p className="text-[11px] font-semibold text-ink-2">热门研究方向</p>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {institutions.flatMap((item) => item.fields).filter((field, index, all) => all.indexOf(field) === index).slice(0, 5).map((field) => (
                  <span key={field} className="rounded-md bg-card px-2 py-1 text-[10px] text-muted shadow-card">{field}</span>
                ))}
              </div>
              <p className="mt-3 text-[10px] leading-relaxed text-faint">按综合排名、论文数量和机构类型浏览科研画像</p>
            </div>
          </div>
        </article>
      </section>

      <section className="mt-5 rounded-2xl bg-card p-5 shadow-card">
        <div className="flex items-center justify-between">
          <div><h2 className="text-sm font-bold text-ink">最近活动</h2><p className="mt-0.5 text-xs text-faint">继续上次的科研探索</p></div>
          <button type="button" className="text-xs text-primary hover:underline">查看全部</button>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {[
            { icon: Clock3, title: "阅读了 Long-Context Reasoning", meta: "论文库 · 2 小时前" },
            { icon: Network, title: "探索了何恺明的合作网络", meta: "学者关系 · 昨天" },
            { icon: TrendingUp, title: "收藏了科学文献知识图谱项目", meta: "项目基金库 · 3 天前" },
          ].map((activity) => (
            <div key={activity.title} className="flex items-center gap-3 rounded-xl bg-panel p-3.5">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-card text-primary shadow-card"><activity.icon className="size-4" /></span>
              <span className="min-w-0"><span className="block truncate text-xs font-medium text-ink">{activity.title}</span><span className="mt-1 block text-[10px] text-faint">{activity.meta}</span></span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

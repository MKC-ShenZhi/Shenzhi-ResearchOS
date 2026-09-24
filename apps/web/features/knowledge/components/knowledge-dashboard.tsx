"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ArrowRight,
  BookOpen,
  Bookmark,
  ChevronRight,
  Landmark,
  Network,
  Search,
  Sparkles,
  Tags,
  Users,
  type LucideIcon,
} from "lucide-react";
import {
  getKnowledgeClient,
  KnowledgeClientError,
  type KnowledgeMixedSearchResponse,
  type KnowledgeMixedSearchType,
  type KnowledgeOverviewResponse,
  type KnowledgePersonalOverviewResponse,
} from "@/clients/knowledge";
import { loadKnowledgeOverview } from "@/features/knowledge/lib/overview-cache";
import { paperHref } from "@/lib/navigation/paper";
import { FeatureNavigationLink } from "@/components/common/feature-availability-provider";

type SearchTab = { label: string; types: KnowledgeMixedSearchType[] };

const SEARCH_TABS: SearchTab[] = [
  { label: "全部", types: ["paper", "scholar", "topic", "project", "patent", "funding", "graph"] },
  { label: "论文", types: ["paper"] },
  { label: "学者", types: ["scholar"] },
  { label: "主题", types: ["topic"] },
  { label: "项目专利基金", types: ["project", "patent", "funding"] },
  { label: "关系图谱", types: ["graph"] },
];

const SEARCH_TYPE_LABELS: Record<KnowledgeMixedSearchType, string> = {
  paper: "论文",
  scholar: "学者",
  topic: "主题",
  project: "项目",
  patent: "专利",
  funding: "基金",
  graph: "关系图谱",
};

const CARDS: Array<{
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  tone: string;
}> = [
  { title: "论文库", description: "检索和探索学术论文，连接论文、主题与引用脉络", href: "/knowledge/search", icon: BookOpen, tone: "bg-primary-soft text-primary" },
  { title: "我的文献", description: "管理收藏、阅读状态和个人科研文献", href: "/knowledge/papers", icon: Bookmark, tone: "bg-brand-violet/10 text-brand-violet" },
  { title: "学者库", description: "搜索学者、研究主题与论文成果", href: "/knowledge/scholars", icon: Users, tone: "bg-success-soft text-success" },
  { title: "主题库", description: "按科研主题探索相关论文", href: "/knowledge/topics", icon: Tags, tone: "bg-brand-cyan/10 text-brand-cyan" },
  { title: "项目基金库", description: "浏览基金并探索关联科研论文", href: "/knowledge/funding", icon: Landmark, tone: "bg-brand-gold/20 text-ink" },
  { title: "关系图谱", description: "从真实论文出发探索引用和知识关系", href: "/knowledge/graph", icon: Network, tone: "bg-primary-soft text-primary" },
];

function StatusText({ status }: { status: string }) {
  if (status === "error") return <span className="text-danger">暂时无法加载</span>;
  if (status === "unsupported") return <span className="text-muted">当前未接入</span>;
  if (status === "pending") return <span className="text-muted">数据准备中</span>;
  if (status === "empty") return <span className="text-muted">暂无数据</span>;
  return null;
}

function CardShell({
  card,
  children,
  className = "",
  bodyClassName = "",
}: {
  card: (typeof CARDS)[number];
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  const Icon = card.icon;
  return (
    <section className={`rounded-3xl bg-card p-6 shadow-card ${className}`}>
      <FeatureNavigationLink href={card.href} className="group flex items-start gap-4">
        <span className={`flex size-12 shrink-0 items-center justify-center rounded-2xl ${card.tone}`}>
          <Icon className="size-6" strokeWidth={1.8} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center justify-between gap-3">
            <span className="text-lg font-bold text-ink group-hover:text-primary">{card.title}</span>
            <ChevronRight className="size-5 shrink-0 text-muted transition-transform group-hover:translate-x-0.5" />
          </span>
          <span className="mt-1 block text-sm leading-6 text-muted">{card.description}</span>
        </span>
      </FeatureNavigationLink>
      <div className={`mt-5 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

function NumberValue({ value, status }: { value: number | null; status: string }) {
  if (value !== null && status === "available") return <span>{value.toLocaleString("zh-CN")}</span>;
  return <StatusText status={status} />;
}

function formatViewedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "浏览时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function graphLabel(value: string, maxLength = 10) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value;
}

function OverviewGraphPreview({ preview }: { preview: KnowledgeOverviewResponse["graphPreview"] }) {
  const root = preview.rootPaperId ? preview.nodes.find((node) => node.id === preview.rootPaperId) : null;
  if (!root) return null;

  const relatedNodeIds: string[] = [];
  for (const edge of preview.edges) {
    const relatedId = edge.sourceId === root.id
      ? edge.targetId
      : edge.targetId === root.id
        ? edge.sourceId
        : null;
    if (relatedId && relatedId !== root.id && !relatedNodeIds.includes(relatedId)) relatedNodeIds.push(relatedId);
  }
  const relatedNodes = relatedNodeIds
    .map((id) => preview.nodes.find((node) => node.id === id))
    .filter((node): node is NonNullable<typeof node> => Boolean(node))
    .slice(0, 6);
  const center = { x: 140, y: 76 };
  const radius = 54;
  const positions = relatedNodes.map((node, index) => {
    const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(relatedNodes.length, 1));
    return { node, x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius };
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-2xl bg-primary-soft/55 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold text-ink">真实论文关系预览</span>
        <span className="text-[11px] text-muted">{relatedNodes.length} 个关联节点</span>
      </div>
      <svg viewBox="0 0 280 154" className="mt-1 min-h-36 flex-1 w-full" role="img" aria-label={`${root.label} 的关系预览图`}>
        {positions.map(({ node, x, y }) => <g key={node.id}>
          <line x1={center.x} y1={center.y} x2={x} y2={y} stroke="currentColor" className="text-primary/30" strokeWidth="1.5" />
          <circle cx={x} cy={y} r="15" className="fill-card stroke-primary/35" strokeWidth="1.5" />
          <text x={x} y={y + 3.5} textAnchor="middle" className="fill-primary text-[7px] font-medium">{graphLabel(node.label, 5)}</text>
        </g>)}
        <circle cx={center.x} cy={center.y} r="25" className="fill-primary stroke-primary" strokeWidth="2" />
        <text x={center.x} y={center.y - 2} textAnchor="middle" className="fill-white text-[8px] font-semibold">论文</text>
        <text x={center.x} y={center.y + 9} textAnchor="middle" className="fill-white text-[7px]">{graphLabel(root.label, 8)}</text>
      </svg>
      <p className="truncate text-center text-xs text-muted" title={root.label}>中心论文：{root.label}</p>
    </div>
  );
}

function SearchResults({ response, query }: { response: KnowledgeMixedSearchResponse; query: string }) {
  const unsupportedLabels = response.unsupportedTypes.map((type) => SEARCH_TYPE_LABELS[type]).join("、");
  const failedLabels = response.failedTypes.map((type) => SEARCH_TYPE_LABELS[type]).join("、");
  const resultLabel = (result: KnowledgeMixedSearchResponse["results"][number]) => (
    result.metadata.matchedBy === "topic" ? SEARCH_TYPE_LABELS.topic : SEARCH_TYPE_LABELS[result.type]
  );

  if (!response.results.length) {
    return <div className="rounded-2xl bg-surface px-4 py-5 text-sm text-muted"><p>没有找到与“{query}”匹配的已接入结果。</p>{unsupportedLabels && <p className="mt-2">{unsupportedLabels}当前未接入。</p>}{failedLabels && <p className="mt-2 text-danger">{failedLabels}暂时不可用，请稍后重试。</p>}</div>;
  }
  return (
    <div className="space-y-3">
      {(unsupportedLabels || failedLabels) && <div className="rounded-xl bg-brand-gold/15 px-4 py-3 text-xs leading-5 text-muted">{unsupportedLabels && <p>{unsupportedLabels}当前未接入，以下仅展示已支持的检索结果。</p>}{failedLabels && <p className={unsupportedLabels ? "mt-1 text-danger" : "text-danger"}>{failedLabels}暂时不可用，请稍后重试。</p>}</div>}
      <div className="divide-y divide-border rounded-2xl bg-surface">
        {response.results.map((result) => (
          <FeatureNavigationLink key={`${result.type}:${result.id}`} href={result.action ?? "/knowledge/search"} className="flex items-center gap-3 px-4 py-3 hover:bg-primary-soft/50">
            <span className="rounded-md bg-card px-2 py-1 text-[11px] font-medium text-primary">{resultLabel(result)}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">{result.title}</span>
              {result.summary && <span className="mt-0.5 block truncate text-xs text-muted">{result.summary}</span>}
            </span>
            <ArrowRight className="size-4 shrink-0 text-muted" />
          </FeatureNavigationLink>
        ))}
      </div>
    </div>
  );
}

export function KnowledgeDashboard() {
  const client = useMemo(() => getKnowledgeClient(), []);
  const [overview, setOverview] = useState<KnowledgeOverviewResponse | null>(null);
  const [personal, setPersonal] = useState<KnowledgePersonalOverviewResponse | null>(null);
  const [overviewError, setOverviewError] = useState(false);
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState(0);
  const [searching, setSearching] = useState(false);
  const [searchResponse, setSearchResponse] = useState<KnowledgeMixedSearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setOverviewError(false);
    const [publicResult, personalResult] = await loadKnowledgeOverview(client);
    if (publicResult.status === "fulfilled") setOverview(publicResult.value);
    else setOverviewError(true);
    if (personalResult.status === "fulfilled") setPersonal(personalResult.value);
  }, [client]);

  useEffect(() => {
    const handle = window.setTimeout(() => { void loadOverview(); }, 0);
    return () => window.clearTimeout(handle);
  }, [loadOverview]);

  const submitSearch = async () => {
    const normalized = query.trim();
    if (!normalized) return;
    setSearching(true);
    setSearchError(null);
    try {
      setSearchResponse(await client.overviewSearch({ query: normalized, types: SEARCH_TABS[activeTab].types, limit: 20 }));
    } catch (error) {
      setSearchResponse(null);
      setSearchError(error instanceof KnowledgeClientError ? error.message : "混合搜索暂时不可用");
    } finally {
      setSearching(false);
    }
  };

  const papers = overview?.paperLibrary;
  const assets = overview?.researchAssets;
  const topicStats = (overview?.topicHighlights ?? [])
    .filter((item) => item.count !== null)
    .sort((left, right) => (right.count ?? 0) - (left.count ?? 0))
    .slice(0, 4);
  const maxTopicCount = topicStats[0]?.count ?? 0;
  const personalFolders = personal?.folders ?? [];
  const recentPapers = personal?.recentPapers ?? [];
  const paperTags = papers?.popularTags.length
    ? papers.popularTags.slice(0, 5).map((tag) => tag.name)
    : (overview?.topicHighlights ?? []).slice(0, 5).map((item) => item.name);

  return (
    <div className="mx-auto max-w-[1440px] px-5 py-6 sm:px-8 lg:px-10 lg:py-8">
      <header className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-ink">知识库</h1>
            <span className="rounded-full bg-primary-soft px-3 py-1 text-sm font-medium text-primary">科研资产中心 · 知识底座</span>
          </div>
          <p className="mt-2 text-base leading-7 text-muted">通过知识底座检索论文、学者与科研主题，并管理你的个人文献和论文关系图谱。</p>
        </div>
        <div className="flex gap-3">
          <Link href="/knowledge/search" className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90"><Search className="size-4" /> 论文检索</Link>
          <FeatureNavigationLink href="/knowledge/graph" className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface"><Network className="size-4" /> 打开关系图谱</FeatureNavigationLink>
        </div>
      </header>

      <section className="mt-7 rounded-3xl bg-card p-5 shadow-card sm:p-6" aria-label="知识库混合搜索">
        <form onSubmit={(event) => { event.preventDefault(); void submitSearch(); }} className="flex items-center gap-3 rounded-2xl border border-primary/15 bg-primary-soft/60 px-4 py-3">
          <Search className="size-5 shrink-0 text-primary/60" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索论文、学者、主题、项目或基金……" className="min-w-0 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-muted" aria-label="搜索论文、学者、主题、项目或基金" />
          <button type="submit" disabled={searching || !query.trim()} className="hidden items-center gap-1 text-sm font-medium text-primary disabled:cursor-not-allowed disabled:opacity-50 sm:inline-flex"><Sparkles className="size-4" /> 跨库检索</button>
        </form>
        <div className="mt-4 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="混合搜索类型">
          {SEARCH_TABS.map((tab, index) => <button key={tab.label} type="button" role="tab" aria-selected={activeTab === index} onClick={() => { setActiveTab(index); setSearchResponse(null); }} className={`shrink-0 rounded-full px-4 py-2 text-sm transition-colors ${activeTab === index ? "bg-primary text-white" : "bg-surface text-muted hover:text-ink"}`}>{tab.label}</button>)}
        </div>
        {(searching || searchError || searchResponse) && <div className="mt-4" aria-live="polite">
          {searching && <div className="rounded-2xl bg-surface px-4 py-5 text-sm text-muted">正在检索知识底座……</div>}
          {!searching && searchError && <div className="rounded-2xl bg-danger-soft px-4 py-5 text-sm text-danger">{searchError}</div>}
          {!searching && searchResponse && <SearchResults response={searchResponse} query={query.trim()} />}
        </div>}
      </section>

      {overviewError && !overview ? <div className="mt-7 rounded-2xl bg-danger-soft px-5 py-4 text-sm text-danger" role="alert">知识库总览数据暂时无法加载。<button type="button" onClick={() => void loadOverview()} className="ml-2 font-medium underline">重试</button></div> : <div className="mt-7 grid gap-5 xl:grid-cols-3">
        <CardShell card={CARDS[0]} className="flex h-full flex-col xl:col-span-2 xl:row-span-2" bodyClassName="flex min-h-0 flex-1 flex-col">
          <div className="grid min-h-0 flex-1 gap-5 xl:grid-cols-[246px_minmax(0,1fr)]">
            <div className="h-full rounded-2xl bg-primary-soft/70 p-5">
              <p className="text-base font-semibold text-ink">论文</p>
              <div className="mt-7 space-y-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-primary/70">全部论文</span>
                  <span className="text-base font-medium text-primary"><NumberValue value={papers?.paperCount ?? null} status={papers?.status ?? "pending"} /></span>
                </div>
                <div className="h-px bg-primary/10" />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-primary/70">已收藏</span>
                  <span className="text-sm text-muted">暂无数据</span>
                </div>
              </div>
            </div>

            <div className="min-h-0 min-w-0 px-1 py-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-base font-semibold text-ink">最近浏览</span>
                <span className="text-sm text-muted">{recentPapers.length ? `共 ${recentPapers.length} 篇` : "暂无数据"}</span>
              </div>
              {recentPapers.length ? <div className="mt-3 divide-y divide-border">{recentPapers.slice(0, 3).map((paper) => <Link key={`${paper.id}-${paper.last_viewed_at}`} href={`/papers/${encodeURIComponent(paper.id)}`} className="group flex items-center gap-4 py-3 first:pt-2 hover:bg-primary-soft/30"><span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary-soft"><BookOpen className="size-5 text-primary" /></span><span className="min-w-0 flex-1"><span className="block truncate text-base text-ink group-hover:text-primary">{paper.title}</span><span className="mt-1 block truncate text-sm text-muted">当前账号最近浏览 · {formatViewedAt(paper.last_viewed_at)}</span></span><ArrowRight className="size-4 shrink-0 text-muted transition-transform group-hover:translate-x-0.5" /></Link>)}</div> : <p className="mt-5 text-sm text-muted">暂无当前账号的最近浏览记录</p>}
            </div>
          </div>
          {paperTags.length ? <div className="mt-5 flex shrink-0 flex-wrap gap-2">{paperTags.map((tag) => <Link key={tag} href={`/knowledge/topics?subject=${encodeURIComponent(tag)}`} className="rounded-full bg-surface px-3.5 py-2 text-xs text-muted transition hover:bg-primary-soft hover:text-primary">#{tag}</Link>)}</div> : null}
        </CardShell>

        <CardShell card={CARDS[1]}>
          {personal?.authRequired ? <div className="rounded-2xl bg-surface p-4"><p className="text-sm text-muted">数据暂无</p><p className="mt-1 text-xs text-muted">登录后查看个人文献数据</p></div> : personalFolders.length ? <div className="grid grid-cols-3 gap-2">{personalFolders.slice(0, 3).map((folder) => <div key={folder.id} className="rounded-xl bg-primary-soft/70 p-3"><div className="text-xl font-bold text-ink">{folder.paperCount}</div><div className="mt-1 truncate text-xs text-muted">{folder.name}</div></div>)}</div> : <p className="rounded-2xl bg-surface p-4 text-sm text-muted">数据暂无</p>}
          {recentPapers[0] ? <p className="mt-4 truncate text-sm text-muted">最近浏览：{recentPapers[0].title}</p> : <p className="mt-4 text-xs text-muted">最近浏览：数据暂无</p>}
        </CardShell>

        <CardShell card={CARDS[2]}>
          {overview?.scholarHighlights.length ? <div className="grid grid-cols-3 gap-2">{overview.scholarHighlights.slice(0, 3).map((item) => <Link key={item.id} href={`/knowledge/scholars/${encodeURIComponent(item.id)}`} className="min-w-0 rounded-xl p-2 hover:bg-success-soft/60"><div className="mx-auto flex size-10 items-center justify-center rounded-full bg-success text-sm font-semibold text-white">{item.name.slice(0, 1)}</div><div className="mt-2 truncate text-center text-sm font-medium text-ink">{item.name}</div><div className="mt-1 truncate text-center text-xs text-muted">{item.count === null ? "数据暂无" : `${item.count.toLocaleString("zh-CN")} 篇论文`}</div></Link>)}</div> : <p className="rounded-2xl bg-surface p-4 text-sm text-muted">数据暂无</p>}
        </CardShell>

        <CardShell card={CARDS[3]} className="flex h-full flex-col" bodyClassName="flex min-h-0 flex-1 flex-col">
          <div className="grid min-h-[280px] flex-1 gap-5 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div className="flex min-h-0 min-w-0 flex-col">
              <p className="text-sm font-semibold text-ink">热门研究主题</p>
              <p className="mt-1 text-xs text-muted">来自知识底座的真实主题</p>
              {papers?.popularTags.length ? <div className="mt-4 flex flex-1 flex-col items-start justify-evenly gap-2">{papers.popularTags.slice(0, 6).map((tag) => <span key={tag.name} className="rounded-lg bg-brand-cyan/10 px-3 py-2 text-xs font-medium text-brand-cyan">{tag.name}</span>)}</div> : overview?.topicHighlights.length ? <div className="mt-4 flex flex-1 flex-col items-start justify-evenly gap-2">{overview.topicHighlights.slice(0, 6).map((item) => <Link key={item.id} href={`/knowledge/topics?subject=${encodeURIComponent(item.metadata.sourceSubject as string ?? item.name)}`} className="rounded-lg bg-brand-cyan/10 px-3 py-2 text-xs font-medium text-brand-cyan transition hover:bg-brand-cyan/20"><span className="block max-w-32 truncate">{item.name}</span></Link>)}</div> : <p className="mt-4 text-xs leading-5 text-muted">暂无真实主题数据</p>}
            </div>
            <div className="flex min-h-0 min-w-0 flex-col border-border md:border-l md:pl-5" role="img" aria-label="四个主题的论文数量柱状图">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-ink">各主题论文数量</p>
                  <p className="mt-1 text-xs text-muted">按主题匹配论文总量排序</p>
                </div>
                {topicStats.length ? <span className="text-xs text-muted">共 {topicStats.length} 项</span> : null}
              </div>
              {topicStats.length ? <div className="mt-4 flex min-h-44 flex-1 items-end gap-2 border-b border-border px-1 sm:gap-3">{topicStats.map((item) => <Link key={item.id} href={`/knowledge/topics?subject=${encodeURIComponent(item.metadata.sourceSubject as string ?? item.name)}`} className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1"><span className="text-[11px] font-semibold text-brand-cyan">{item.count?.toLocaleString("zh-CN")}</span><span className="relative flex min-h-28 flex-1 w-full max-w-9 items-end overflow-hidden rounded-t-lg bg-brand-cyan/15"><span className="w-full rounded-t-lg bg-brand-cyan/80 transition-all group-hover:bg-primary" style={{ height: `${Math.max(14, ((item.count ?? 0) / maxTopicCount) * 100)}%` }} /></span><span className="w-full truncate text-center text-[10px] text-muted group-hover:text-primary" title={item.name}>{item.name}</span></Link>)}</div> : <p className="mt-4 rounded-xl bg-surface px-3 py-3 text-xs leading-5 text-muted">暂无真实主题论文数量统计</p>}
            </div>
          </div>
        </CardShell>

        <CardShell card={CARDS[4]}>
          <div className="rounded-2xl bg-primary-soft/70 px-4 py-3">
            <div className="text-sm text-muted">资产总量</div>
            <div className="mt-1 text-3xl font-bold text-ink"><NumberValue value={assets?.total ?? null} status={assets?.status ?? "pending"} /></div>
            <div className="mt-1 text-xs text-muted">统一 Funding 资产，不拆分项目、专利、基金类型</div>
          </div>
          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold text-ink">资产信息</span>
              <span className="text-xs text-muted">知识底座实时返回</span>
            </div>
            {assets?.highlights?.length ? <div className="space-y-2">{assets.highlights.slice(0, 3).map((item) => <Link key={item.id} href={`/knowledge/funding?funding=${encodeURIComponent(item.id)}`} className="flex items-center justify-between rounded-xl bg-brand-gold/15 px-4 py-2.5 hover:bg-brand-gold/25"><span className="min-w-0 truncate text-sm font-medium text-ink">{item.name}</span><span className="ml-3 shrink-0 text-xs text-muted">{item.count === null ? "基金" : `${item.count.toLocaleString("zh-CN")} 篇论文`}</span></Link>)}</div> : <p className="rounded-xl bg-surface px-4 py-3 text-sm text-muted">暂无可展示的真实基金资产信息</p>}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted">项目、专利暂无独立实体接口，暂不展示虚构资产。</p>
        </CardShell>

        <CardShell card={CARDS[5]} className="flex h-full flex-col" bodyClassName="flex min-h-0 flex-1 flex-col">
          {overview?.graphPreview.supported && overview.graphPreview.rootPaperId ? <Link href={paperHref(overview.graphPreview.rootPaperId, { mode: "create", source: "/knowledge", graph: true })} className="group flex min-h-0 flex-1 flex-col">
            <OverviewGraphPreview preview={overview.graphPreview} />
            <span className="mt-3 inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary group-hover:underline">查看完整关系图谱 <ArrowRight className="size-3.5" /></span>
          </Link> : <div className="rounded-2xl bg-primary-soft/70 p-4 text-sm leading-6 text-muted">{overview?.graphPreview.status === "error" ? "关系图谱暂时无法加载，请稍后重试。" : "当前暂无可展示的真实论文关系图谱。"}</div>}
        </CardShell>
      </div>}
    </div>
  );
}

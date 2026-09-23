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
  { title: "项目专利基金库", description: "按项目、专利或基金探索关联科研成果", href: "/knowledge/funding", icon: Landmark, tone: "bg-brand-gold/20 text-ink" },
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
}: {
  card: (typeof CARDS)[number];
  children: ReactNode;
  className?: string;
}) {
  const Icon = card.icon;
  return (
    <section className={`rounded-3xl bg-card p-6 shadow-card ${className}`}>
      <Link href={card.href} className="group flex items-start gap-4">
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
      </Link>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function NumberValue({ value, status }: { value: number | null; status: string }) {
  if (value !== null && status === "available") return <span>{value.toLocaleString("zh-CN")}</span>;
  return <StatusText status={status} />;
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
          <Link key={`${result.type}:${result.id}`} href={result.action ?? "/knowledge/search"} className="flex items-center gap-3 px-4 py-3 hover:bg-primary-soft/50">
            <span className="rounded-md bg-card px-2 py-1 text-[11px] font-medium text-primary">{resultLabel(result)}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">{result.title}</span>
              {result.summary && <span className="mt-0.5 block truncate text-xs text-muted">{result.summary}</span>}
            </span>
            <ArrowRight className="size-4 shrink-0 text-muted" />
          </Link>
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
  const personalFolders = personal?.folders ?? [];
  const recentPapers = personal?.recentPapers ?? papers?.recentPapers ?? [];

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
          <Link href="/knowledge/graph" className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface"><Network className="size-4" /> 打开关系图谱</Link>
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
        <CardShell card={CARDS[0]} className="xl:col-span-2 xl:row-span-2">
          <div>
            <div className="text-sm font-medium text-muted">知识底座可检索论文</div>
            <div className="mt-2 text-4xl font-bold text-ink"><NumberValue value={papers?.paperCount ?? null} status={papers?.status ?? "pending"} /></div>
            {overview?.asOf && <div className="mt-1 text-xs text-muted">统计于 {new Date(overview.asOf).toLocaleString("zh-CN")}</div>}
            <div className="mt-5 divide-y divide-border rounded-2xl bg-surface">{recentPapers.length ? recentPapers.slice(0, 3).map((paper) => <Link key={paper.id} href={`/papers/${encodeURIComponent(paper.id)}`} className="flex items-center gap-3 px-4 py-3 hover:bg-primary-soft/50"><BookOpen className="size-4 shrink-0 text-primary" /><span className="truncate text-sm text-ink">{paper.title}</span></Link>) : <p className="px-4 py-4 text-sm text-muted">暂无当前账号的最近浏览记录</p>}</div>
          </div>
        </CardShell>

        <CardShell card={CARDS[1]}>
          {personal?.authRequired ? <div className="rounded-2xl bg-surface p-4"><p className="text-sm text-muted">数据暂无</p><p className="mt-1 text-xs text-muted">登录后查看个人文献数据</p></div> : personalFolders.length ? <div className="grid grid-cols-3 gap-2">{personalFolders.slice(0, 3).map((folder) => <div key={folder.id} className="rounded-xl bg-primary-soft/70 p-3"><div className="text-xl font-bold text-ink">{folder.paperCount}</div><div className="mt-1 truncate text-xs text-muted">{folder.name}</div></div>)}</div> : <p className="rounded-2xl bg-surface p-4 text-sm text-muted">数据暂无</p>}
          {recentPapers[0] ? <p className="mt-4 truncate text-sm text-muted">最近浏览：{recentPapers[0].title}</p> : <p className="mt-4 text-xs text-muted">最近浏览：数据暂无</p>}
        </CardShell>

        <CardShell card={CARDS[2]}>
          {overview?.scholarHighlights.length ? <div className="grid grid-cols-3 gap-2">{overview.scholarHighlights.slice(0, 3).map((item) => <Link key={item.id} href={`/knowledge/scholars/${encodeURIComponent(item.id)}`} className="min-w-0 rounded-xl p-2 hover:bg-success-soft/60"><div className="mx-auto flex size-10 items-center justify-center rounded-full bg-success text-sm font-semibold text-white">{item.name.slice(0, 1)}</div><div className="mt-2 truncate text-center text-sm font-medium text-ink">{item.name}</div><div className="mt-1 truncate text-center text-xs text-muted">{item.count === null ? "数据暂无" : `${item.count.toLocaleString("zh-CN")} 篇论文`}</div></Link>)}</div> : <p className="rounded-2xl bg-surface p-4 text-sm text-muted">数据暂无</p>}
        </CardShell>

        <CardShell card={CARDS[3]}>
          <div className="rounded-2xl bg-brand-cyan/10 p-4">
            <p className="text-sm font-semibold text-ink">热门主题</p>
            {papers?.popularTags.length ? <div className="mt-3 flex flex-wrap gap-2">{papers.popularTags.map((tag) => <span key={tag.name} className="rounded-full bg-card px-3 py-1.5 text-xs text-brand-cyan">#{tag.name}{tag.count === null ? "" : ` · ${tag.count}`}</span>)}</div> : overview?.topicHighlights.length ? <div className="mt-3 flex flex-wrap gap-2">{overview.topicHighlights.map((item) => <span key={item.id} className="rounded-full bg-card px-3 py-1.5 text-xs text-brand-cyan">{item.name}{item.count === null ? "" : ` · ${item.count}`}</span>)}</div> : <p className="mt-3 text-xs leading-5 text-muted">暂无真实主题统计</p>}
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
            {assets?.highlights?.length ? <div className="space-y-2">{assets.highlights.slice(0, 3).map((item) => <Link key={item.id} href={`/knowledge/funding?funding=${encodeURIComponent(item.name)}`} className="flex items-center justify-between rounded-xl bg-brand-gold/15 px-4 py-2.5 hover:bg-brand-gold/25"><span className="min-w-0 truncate text-sm font-medium text-ink">{item.name}</span><span className="ml-3 shrink-0 text-xs text-muted">{item.count === null ? "基金" : `${item.count.toLocaleString("zh-CN")} 篇论文`}</span></Link>)}</div> : <p className="rounded-xl bg-surface px-4 py-3 text-sm text-muted">暂无可展示的真实基金资产信息</p>}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted">项目、专利暂无独立实体接口，暂不展示虚构资产。</p>
        </CardShell>

        <CardShell card={CARDS[5]}>{overview?.graphPreview.supported ? <p className="text-sm text-muted">已加载 {overview.graphPreview.nodes.length} 个节点和 {overview.graphPreview.edges.length} 条关系。</p> : <div className="rounded-2xl bg-primary-soft/70 p-4 text-sm leading-6 text-muted">请选择一篇真实论文后查看关系图谱，当前没有默认中心论文。</div>}</CardShell>
      </div>}
    </div>
  );
}

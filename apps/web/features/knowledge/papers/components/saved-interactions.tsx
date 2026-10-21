"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Search, Shapes } from "lucide-react";
import { fetchMyCollectedPapers, fetchMyLikes, fetchMyTopicFollows } from "@/clients/backend/interactions";
import type { LikedPaperItem, LikedPaperListResponse, TopicFollowListResponse } from "@/clients/backend/interactions";
import { ApiError } from "@/clients/backend/http";
import { useAuth } from "@/components/auth/auth-provider";
import { getKnowledgeClient } from "@/clients/knowledge";
import type { CollectionPaperItem, CollectionPaperListResponse, KnowledgeTopic } from "@/clients/knowledge";
import { usePaperLike } from "@/features/knowledge/interactions/use-paper-like";
import { useRefreshPaperInteraction } from "@/features/knowledge/interactions/use-refresh-paper-interaction";
import { useTopicFollow } from "@/features/knowledge/interactions/use-topic-follow";
import { paperHref } from "@/lib/navigation/paper";
import { topicHref } from "@/features/knowledge/topics/topic-url-state";
import { useCollections } from "@/stores/collections";

type Tab = "likes" | "collections" | "topics";
const PAGE_SIZE = 20;
const TABS: { id: Tab; label: string }[] = [
  { id: "likes", label: "点赞的论文" },
  { id: "collections", label: "收藏的论文" },
  { id: "topics", label: "关注的主题" },
];

export function SavedInteractions({ userId }: { userId: string | null }) {
  const [tab, setTab] = useState<Tab>("likes");
  const [query, setQuery] = useState("");
  const [pages, setPages] = useState({ likes: 1, collections: 1 });
  const enabled = Boolean(userId);
  const likes = useQuery({
    queryKey: ["my-likes", userId, pages.likes],
    queryFn: () => fetchMyLikes(pages.likes, PAGE_SIZE),
    enabled,
    retry: false,
  });
  const collections = useQuery({
    queryKey: ["my-collected-papers", userId, pages.collections],
    queryFn: () => fetchMyCollectedPapers(pages.collections, PAGE_SIZE),
    enabled,
    retry: false,
  });
  const follows = useQuery({
    queryKey: ["my-topic-follows", userId],
    queryFn: fetchMyTopicFollows,
    enabled,
    retry: false,
  });
  const topics = useQuery({
    queryKey: ["knowledge", "topics"],
    queryFn: () => getKnowledgeClient().topics(),
    enabled: enabled && tab === "topics" && Boolean(follows.data?.items.length),
    staleTime: 15 * 60_000,
    retry: false,
  });
  const active = tab === "likes" ? likes : tab === "collections" ? collections : follows;
  const total = tab === "likes" ? likes.data?.total : tab === "collections" ? collections.data?.total : follows.data?.total;
  const label = TABS.find((item) => item.id === tab)!.label;
  const term = query.trim().toLocaleLowerCase();
  const paperItems: (LikedPaperItem | CollectionPaperItem)[] = tab === "likes"
    ? likes.data?.items ?? [] : tab === "collections" ? collections.data?.items ?? [] : [];
  const visiblePapers = paperItems.filter((paper) =>
    `${paper.title} ${paper.authors.join(" ")} ${paper.venue ?? ""}`.toLocaleLowerCase().includes(term));
  const topicById = new Map((topics.data?.items ?? []).map((item) => [item.id, item]));
  const visibleTopics = (follows.data?.items ?? []).filter((item) => {
    const topic = topicById.get(item.topic_id);
    return `${topic?.nameZh ?? ""} ${topic?.nameEn ?? ""} ${topic?.category ?? ""}`.toLocaleLowerCase().includes(term);
  });
  const page = tab === "likes" ? pages.likes : pages.collections;
  const pageCount = Math.max(1, Math.ceil((total ?? 0) / PAGE_SIZE));
  const handlePaperRemoved = () => {
    if (page > 1 && paperItems.length === 1) {
      setPages((current) => ({ ...current, [tab]: page - 1 }));
    }
  };

  return (
    <section className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-5 lg:h-full lg:min-h-0 lg:p-8" aria-label="点赞与收藏">
      <div className="min-h-full rounded-2xl bg-card p-4 shadow-card sm:p-6">
        <div role="tablist" aria-label="我的互动分类" className="flex gap-2 overflow-x-auto border-b border-line pb-3">
          {TABS.map((item) => {
            const count = item.id === "likes" ? likes.data?.total : item.id === "collections" ? collections.data?.total : follows.data?.total;
            return <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} onClick={() => { setTab(item.id); setQuery(""); }} className={`shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-primary ${tab === item.id ? "bg-primary-soft text-primary" : "text-muted hover:bg-panel hover:text-ink"}`}>{item.label} <span className="ml-2 tabular-nums text-xs">{count ?? "—"}</span></button>;
          })}
        </div>

        <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
          <div><h2 className="text-lg font-semibold text-ink">{label}</h2><p className="mt-1 text-xs text-faint">{tab === "likes" ? "按最近点赞排序" : tab === "collections" ? "跨文件夹汇总，同一论文只显示一次" : "按最近关注排序"} · 搜索当前页</p></div>
          <label className="relative w-full sm:w-64"><span className="sr-only">搜索{label}</span><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`搜索${label}`} className="h-10 w-full rounded-xl border border-line bg-background pl-9 pr-3 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/15" /></label>
        </div>

        {!userId ? <Status>登录后可查看自己的点赞、收藏和关注记录。</Status>
          : active.isPending || (tab === "topics" && follows.data?.items.length && topics.isPending) ? <Status>正在加载…</Status>
          : active.isError || (tab === "topics" && follows.data?.items.length && topics.isError) ? <Status>加载失败，请稍后重试。<button type="button" onClick={() => void (tab === "topics" && topics.isError ? topics.refetch() : active.refetch())} className="ml-2 font-medium text-primary underline underline-offset-2">重试</button></Status>
          : tab === "topics" ? <div className="mt-6 space-y-2">{visibleTopics.length ? visibleTopics.map((item) => <TopicRow key={item.topic_id} topicId={item.topic_id} topic={topicById.get(item.topic_id)} userId={userId} />) : <Status>{term ? "当前页没有匹配的主题" : "还没有关注的主题"}</Status>}</div>
          : <div className="mt-6 space-y-2">{visiblePapers.length ? visiblePapers.map((paper) => <PaperRow key={paper.paper_id} paper={paper} liked={tab === "likes"} userId={userId} onRemoved={handlePaperRemoved} />) : <Status>{term ? "当前页没有匹配的论文" : tab === "likes" ? "还没有点赞的论文" : "还没有收藏的论文"}</Status>}</div>}

        {userId && tab !== "topics" && !active.isError && pageCount > 1 && <div className="mt-6 flex items-center justify-center gap-4 text-sm text-muted"><button type="button" disabled={page <= 1} onClick={() => setPages((current) => ({ ...current, [tab]: page - 1 }))} className="rounded-lg px-3 py-2 hover:bg-panel disabled:opacity-40">上一页</button><span className="tabular-nums">{page} / {pageCount}</span><button type="button" disabled={page >= pageCount} onClick={() => setPages((current) => ({ ...current, [tab]: page + 1 }))} className="rounded-lg px-3 py-2 hover:bg-panel disabled:opacity-40">下一页</button></div>}
      </div>
    </section>
  );
}

function PaperRow({ paper, liked, userId, onRemoved }: {
  paper: LikedPaperItem | CollectionPaperItem;
  liked: boolean;
  userId: string | null;
  onRemoved: () => void;
}) {
  const queryClient = useQueryClient();
  const { openLogin } = useAuth();
  const { toggle, isSaving: isLikeSaving } = usePaperLike(paper.paper_id);
  const updatePaperFolders = useCollections((state) => state.updatePaperFolders);
  const refreshInteraction = useRefreshPaperInteraction(paper.paper_id);
  const [isCollectionSaving, setCollectionSaving] = useState(false);
  const [error, setError] = useState("");
  const saving = isLikeSaving || isCollectionSaving;

  async function cancel() {
    if (saving || !userId) return;
    setError("");
    try {
      if (liked) {
        await toggle(true);
        queryClient.setQueriesData<LikedPaperListResponse>({ queryKey: ["my-likes", userId] }, (current) => current && ({
          ...current,
          items: current.items.filter((item) => item.paper_id !== paper.paper_id),
          total: Math.max(0, current.total - 1),
        }));
        onRemoved();
        await queryClient.invalidateQueries({ queryKey: ["my-likes", userId] });
      } else {
        setCollectionSaving(true);
        await updatePaperFolders(paper.paper_id, []);
        await refreshInteraction();
        queryClient.setQueriesData<CollectionPaperListResponse>({ queryKey: ["my-collected-papers", userId] }, (current) => current && ({
          ...current,
          items: current.items.filter((item) => item.paper_id !== paper.paper_id),
          total: Math.max(0, current.total - 1),
        }));
        onRemoved();
        await queryClient.invalidateQueries({ queryKey: ["my-collected-papers", userId] });
      }
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) openLogin({ notice: "登录状态已失效，请重新登录" });
      setError("取消失败，请重试");
    } finally {
      setCollectionSaving(false);
    }
  }

  return <div className="rounded-xl border border-line px-3 py-3 sm:px-4">
    <div className="flex items-center gap-3">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><FileText className="size-5" /></span>
      <div className="min-w-0 flex-1"><Link href={paperHref(paper.paper_id, { mode: "create", source: "/knowledge/papers" })} className="block truncate text-sm font-semibold text-ink hover:text-primary hover:underline">{paper.title}</Link><p className="mt-1 truncate text-xs text-faint">{paper.venue ?? "暂无会议"} · {paper.year ?? "年份未知"} · {paper.authors.join("、") || "作者未知"}</p></div>
      <CancelButton action={liked ? "点赞" : "收藏"} saving={saving} onClick={() => void cancel()} />
      <Link href={paperHref(paper.paper_id, { mode: "create", source: "/knowledge/papers" })} className="shrink-0 text-xs font-medium text-primary hover:underline">查看论文 ›</Link>
    </div>
    {error && <p role="alert" className="mt-2 text-right text-xs text-danger">{error}</p>}
  </div>;
}

function TopicRow({ topicId, topic, userId }: { topicId: string; topic: KnowledgeTopic | undefined; userId: string | null }) {
  const queryClient = useQueryClient();
  const { openLogin } = useAuth();
  const { toggle, isSaving } = useTopicFollow(topicId);
  const [error, setError] = useState("");

  async function cancel() {
    if (isSaving || !userId) return;
    setError("");
    try {
      await toggle(true);
      queryClient.setQueryData<TopicFollowListResponse>(["my-topic-follows", userId], (current) => current && ({
        ...current,
        items: current.items.filter((item) => item.topic_id !== topicId),
        total: Math.max(0, current.total - 1),
      }));
      await queryClient.invalidateQueries({ queryKey: ["my-topic-follows", userId] });
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) openLogin({ notice: "登录状态已失效，请重新登录" });
      setError("取消失败，请重试");
    }
  }

  return <div className="rounded-xl border border-line px-3 py-3 sm:px-4">
    <div className="flex items-center gap-3">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><Shapes className="size-5" /></span>
      <div className="min-w-0 flex-1">{topic ? <Link href={topicHref(topic.id)} className="block truncate text-sm font-semibold text-ink hover:text-primary hover:underline">{topic.nameZh}</Link> : <p className="text-sm font-semibold text-ink">已下架主题</p>}<p className="mt-1 truncate text-xs text-faint">{topic ? `${topic.category} · ${topic.descriptionZh}` : "主题暂不可查看"}</p></div>
      <CancelButton action="关注" saving={isSaving} onClick={() => void cancel()} />
      {topic && <Link href={topicHref(topic.id)} className="shrink-0 text-xs font-medium text-primary hover:underline">查看主题 ›</Link>}
    </div>
    {error && <p role="alert" className="mt-2 text-right text-xs text-danger">{error}</p>}
  </div>;
}

function CancelButton({ action, saving, onClick }: { action: "点赞" | "收藏" | "关注"; saving: boolean; onClick: () => void }) {
  return <button type="button" aria-label={`取消${action}`} title={`取消${action}`} disabled={saving} onClick={onClick} className="group inline-flex min-w-20 shrink-0 cursor-pointer justify-center rounded-lg bg-success-soft px-2.5 py-1.5 text-xs font-medium text-success transition-colors hover:bg-danger-soft hover:text-danger focus-visible:bg-danger-soft focus-visible:text-danger focus-visible:outline-2 focus-visible:outline-danger disabled:cursor-progress disabled:opacity-60">
    {saving ? "处理中…" : <><span className="group-hover:hidden group-focus-visible:hidden">已{action}</span><span className="hidden group-hover:inline group-focus-visible:inline">取消{action}</span></>}
  </button>;
}

function Status({ children }: { children: React.ReactNode }) {
  return <div className="mt-6 rounded-xl bg-panel px-5 py-10 text-center text-sm text-muted">{children}</div>;
}

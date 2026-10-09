"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getKnowledgeClient } from "@/clients/knowledge";
import { TopicCategoryTabs } from "./topic-category-tabs";
import { TopicGrid } from "./topic-grid";
import { filterTopics, groupTopics, readTopicViewState } from "./topic-url-state";
import { TopicEmptyState, TopicErrorState, TopicLoadingState } from "./topic-states";
import { TopicSearch } from "./topic-search";

export function TopicsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = readTopicViewState(new URLSearchParams(searchParams.toString()));
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["knowledge", "topics"],
    queryFn: ({ signal }) => getKnowledgeClient().topics(signal),
  });

  const updateState = (next: Partial<typeof state>) => {
    const params = new URLSearchParams(searchParams.toString());
    const query = next.query ?? state.query;
    const category = next.category ?? state.category;
    if (query) params.set("q", query); else params.delete("q");
    if (category) params.set("category", category); else params.delete("category");
    router.replace(`${pathname}${params.size ? `?${params.toString()}` : ""}`, { scroll: false });
  };

  const topics = data?.items ?? [];
  const visibleTopics = filterTopics(topics, state);
  const featuredTopics = state.category || state.query ? [] : topics.slice(0, 3);
  const groups = groupTopics(visibleTopics);

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-7">
          <p className="mb-2 text-sm font-medium tracking-[0.16em] text-primary">SHENZHI TOPICS</p>
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div><h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">主题广场</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">发现值得持续追踪的研究主题，让论文、方向与问题形成清晰的知识入口。</p></div>
            <div className="w-full lg:max-w-md"><TopicSearch value={state.query} onChange={(query) => updateState({ query })} /></div>
          </div>
        </header>
        <div className="mb-8"><TopicCategoryTabs categories={data?.categories ?? []} value={state.category} onChange={(category) => updateState({ category })} /></div>
        {isPending ? <TopicLoadingState /> : isError ? <TopicErrorState onRetry={() => void refetch()} /> : visibleTopics.length === 0 ? <TopicEmptyState onReset={() => updateState({ query: "", category: "" })} /> : (
          <div className="space-y-10">
            {featuredTopics.length > 0 ? <section><div className="mb-4 flex items-end justify-between gap-4"><div><h2 className="text-xl font-semibold text-foreground">精选主题</h2><p className="mt-1 text-sm text-muted-foreground">从当前主题库中优先展示的研究入口</p></div><span className="text-xs text-muted-foreground">{data?.total ?? 0} 个主题</span></div><TopicGrid topics={featuredTopics} featured /></section> : null}
            {groups.map(([category, categoryTopics]) => <section key={category}><div className="mb-4 flex items-end justify-between gap-4"><div><h2 className="text-xl font-semibold text-foreground">{category}</h2><p className="mt-1 text-sm text-muted-foreground">按研究方向浏览主题</p></div><span className="text-xs text-muted-foreground">{categoryTopics.length} 个主题</span></div><TopicGrid topics={categoryTopics} /></section>)}
          </div>
        )}
      </div>
    </main>
  );
}

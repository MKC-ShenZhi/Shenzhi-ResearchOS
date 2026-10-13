"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getKnowledgeClient } from "@/clients/knowledge";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import { TopicCategoryTabs } from "./topic-category-tabs";
import { TopicGrid } from "./topic-grid";
import { filterTopics, groupTopics, readTopicViewState, updateTopicViewParams } from "./topic-url-state";
import { TopicEmptyState, TopicErrorState, TopicLoadingState } from "./topic-states";
import { TopicSearch } from "./topic-search";
import { selectFeaturedTopics } from "./topic-metadata";

export function TopicsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const returnTo = useCurrentInternalPath();
  const state = readTopicViewState(new URLSearchParams(searchParams.toString()));
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["knowledge", "topics"],
    queryFn: ({ signal }) => getKnowledgeClient().topics(signal),
  });

  const updateState = (next: Partial<typeof state>) => {
    const params = updateTopicViewParams(new URLSearchParams(searchParams.toString()), next);
    if (params.toString() === searchParams.toString()) return;
    router.push(`${pathname}${params.size ? `?${params.toString()}` : ""}`, { scroll: false });
  };

  const topics = data?.items ?? [];
  const visibleTopics = filterTopics(topics, state);
  const featuredTopics = state.category || state.query ? [] : selectFeaturedTopics(topics);
  const groups = groupTopics(visibleTopics);

  return (
    <main className="min-h-screen bg-white px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1180px]">
        <header className="mb-7">
          <div className="mb-4"><TopicSearch value={state.query} onSearch={(query) => updateState({ query })} /></div>
          <TopicCategoryTabs categories={data?.categories ?? []} value={state.category} onChange={(category) => updateState({ category })} />
        </header>
        {isPending ? <TopicLoadingState /> : isError ? <TopicErrorState onRetry={() => void refetch()} /> : visibleTopics.length === 0 ? <TopicEmptyState onReset={() => updateState({ query: "", category: "" })} /> : (
          <div className="space-y-10">
            {featuredTopics.length > 0 ? <section><div className="mb-3 flex items-center justify-between gap-4"><h2 className="text-2xl font-semibold tracking-tight text-foreground">精选主题</h2><span className="text-sm text-muted-foreground">{data?.total ?? 0} 个主题</span></div><TopicGrid topics={featuredTopics} returnTo={returnTo} featured /></section> : null}
            {groups.map(([category, categoryTopics]) => <section key={category}><div className="mb-3 flex items-center justify-between gap-4"><h2 className="text-2xl font-semibold tracking-tight text-foreground">{category}</h2><span className="text-sm text-muted-foreground">{categoryTopics.length} 个主题</span></div><TopicGrid topics={categoryTopics} returnTo={returnTo} carousel={!state.category && categoryTopics.length > 3} /></section>)}
          </div>
        )}
      </div>
    </main>
  );
}

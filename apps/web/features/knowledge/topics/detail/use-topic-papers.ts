"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { getKnowledgeClient } from "@/clients/knowledge";
import { knowledgeQueryRetry } from "@/features/knowledge/retry";

const TOPIC_PAPER_PAGE_SIZE = 10;

export function useTopicPapers(topicId: string, subjectQuery: string) {
  const query = useInfiniteQuery({
    queryKey: ["knowledge", "topic-papers", topicId, subjectQuery],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      getKnowledgeClient().searchBySubject(
        subjectQuery,
        pageParam,
        TOPIC_PAPER_PAGE_SIZE,
        signal,
      ),
    getNextPageParam: (lastPage, pages) => {
      const loadedCount = pages.reduce(
        (count, page) => count + page.results.length,
        0,
      );

      if (lastPage.results.length === 0 || loadedCount >= lastPage.total) {
        return undefined;
      }

      return loadedCount;
    },
    enabled: Boolean(topicId && subjectQuery.trim()),
    retry: knowledgeQueryRetry,
  });

  return {
    ...query,
    papers: query.data?.pages.flatMap((page) => page.results) ?? [],
    total: query.data?.pages[0]?.total ?? 0,
  };
}

"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { getKnowledgeClient } from "@/clients/knowledge";
import { topicPaperQueryOptions } from "./topic-paper-query";

export function useTopicPapers(topicId: string) {
  const query = useInfiniteQuery(topicPaperQueryOptions(
    topicId,
    (...args) => getKnowledgeClient().topicPapers(...args),
  ));
  const pages = query.data?.pages ?? [];
  const lastPage = pages.at(-1);
  // Pagination counts raw results; overlapping upstream pages render each paper once.
  const papers = [...new Map(pages.flatMap((page) => page.results).map((paper) => [paper.id, paper])).values()];

  return {
    ...query,
    papers,
    total: lastPage?.total ?? 0,
  };
}

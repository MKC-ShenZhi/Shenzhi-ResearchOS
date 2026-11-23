import { infiniteQueryOptions, type InfiniteData } from "@tanstack/react-query";
import type { KnowledgeClient, KnowledgePaperBrowseResponse } from "../../../../clients/knowledge";
import { knowledgeQueryRetry } from "../../retry";

export const TOPIC_PAPER_PAGE_SIZE = 10;
export function nextTopicPaperOffset(page: KnowledgePaperBrowseResponse) {
  const nextOffset = page.offset + page.results.length;
  return page.results.length && nextOffset < page.total ? nextOffset : undefined;
}

export function canAutoLoadTopicPapers(state: { hasNextPage: boolean; isFetching: boolean; isError: boolean }) {
  return state.hasNextPage && !state.isFetching && !state.isError;
}

export function topicPaperQueryOptions(
  topicId: string,
  topicPapers: KnowledgeClient["topicPapers"],
) {
  return infiniteQueryOptions<KnowledgePaperBrowseResponse, Error, InfiniteData<KnowledgePaperBrowseResponse, number>, string[], number>({
    queryKey: ["knowledge", "openalex-topic-papers", topicId],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => topicPapers(topicId, pageParam, TOPIC_PAPER_PAGE_SIZE, signal),
    getNextPageParam: nextTopicPaperOffset,
    enabled: Boolean(topicId),
    staleTime: 5 * 60_000,
    retry: knowledgeQueryRetry,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

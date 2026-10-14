import { infiniteQueryOptions, type InfiniteData } from "@tanstack/react-query";
import type { KnowledgeClient, KnowledgeSubjectSearchResponse } from "../../../../clients/knowledge";
import { knowledgeQueryRetry } from "../../retry";

export const TOPIC_PAPER_PAGE_SIZE = 10;
// ShenZhi Subject Search accepts offset < 1000. Keep this in sync with the API.
export const TOPIC_PAPER_RESULT_LIMIT = 1000;

export function nextTopicPaperOffset(page: KnowledgeSubjectSearchResponse, offset: number) {
  const nextOffset = offset + page.results.length;
  if (!page.results.length || nextOffset >= page.total || nextOffset >= TOPIC_PAPER_RESULT_LIMIT) {
    return undefined;
  }
  return nextOffset;
}

export function topicPaperLimitReached(page: KnowledgeSubjectSearchResponse, offset: number) {
  const loaded = offset + page.results.length;
  return loaded >= TOPIC_PAPER_RESULT_LIMIT && loaded < page.total;
}

export function canAutoLoadTopicPapers(state: { hasNextPage: boolean; isFetching: boolean; isError: boolean }) {
  return state.hasNextPage && !state.isFetching && !state.isError;
}

export function topicPaperQueryOptions(
  topicId: string,
  subjectQuery: string,
  searchBySubject: KnowledgeClient["searchBySubject"],
) {
  return infiniteQueryOptions<KnowledgeSubjectSearchResponse, Error, InfiniteData<KnowledgeSubjectSearchResponse, number>, string[], number>({
    queryKey: ["knowledge", "topic-papers", topicId, subjectQuery],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => searchBySubject(
      subjectQuery,
      pageParam,
      Math.min(TOPIC_PAPER_PAGE_SIZE, TOPIC_PAPER_RESULT_LIMIT - pageParam),
      signal,
    ),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextTopicPaperOffset(lastPage, lastPageParam),
    enabled: Boolean(topicId && subjectQuery.trim()),
    retry: knowledgeQueryRetry,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

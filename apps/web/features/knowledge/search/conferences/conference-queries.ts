"use client";

import { queryOptions } from "@tanstack/react-query";
import { getKnowledgeClient, type KnowledgeClient, type KnowledgePaperBrowseParams } from "../../../../clients/knowledge";
import { knowledgeQueryRetry } from "../../retry";

export function conferenceQueryOptions(client: KnowledgeClient = getKnowledgeClient()) {
  return queryOptions({
    queryKey: ["knowledge", "conferences"],
    queryFn: ({ signal }) => client.conferences(signal),
    staleTime: 10 * 60_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
    retry: knowledgeQueryRetry,
  });
}

export function paperBrowseQueryOptions(params: KnowledgePaperBrowseParams, client: KnowledgeClient = getKnowledgeClient()) {
  return queryOptions({
    queryKey: ["knowledge", "paper-browse", params],
    queryFn: ({ signal }) => client.browsePapers(params, signal),
    staleTime: 2 * 60_000,
    gcTime: 5 * 60_000,
    retry: knowledgeQueryRetry,
  });
}

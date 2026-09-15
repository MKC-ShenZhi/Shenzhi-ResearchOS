"use client";

import { useQuery } from "@tanstack/react-query";
import { getKnowledgeClient } from "@/clients/knowledge";
import { knowledgeQueryRetry } from "../retry";

/** Detail and graph share the same paper cache and failure policy. */
export function useKnowledgePaper(paperId: string | null) {
  return useQuery({
    queryKey: ["knowledge", "paper", paperId],
    queryFn: () => getKnowledgeClient().paper(paperId!),
    enabled: Boolean(paperId),
    staleTime: 60_000,
    retry: knowledgeQueryRetry,
  });
}

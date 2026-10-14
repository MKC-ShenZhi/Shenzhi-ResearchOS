"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
    getKnowledgeClient,
    type KnowledgeTopic,
    type KnowledgeTopicListResponse,
} from "@/clients/knowledge";
import { findTopicMetadata, toTopicMetadata } from "../topic-metadata";

const TOPICS_QUERY_KEY = ["knowledge", "topics"] as const;

export function topicDetailQueryKey(topicId: string) {
    return ["knowledge", "topic", topicId] as const;
}

export function useTopicDetail(topicId: string) {
    const queryClient = useQueryClient();
    const topicList =
        queryClient.getQueryData<KnowledgeTopicListResponse>(TOPICS_QUERY_KEY);
    const cachedTopic = topicList
        ? findTopicMetadata(topicList.items, topicId)
        : undefined;

    return useQuery<KnowledgeTopic>({
        queryKey: topicDetailQueryKey(topicId),
        queryFn: async ({ signal }) =>
            toTopicMetadata(await getKnowledgeClient().topic(topicId, signal)),
        placeholderData: cachedTopic,
        enabled: Boolean(topicId),
    });
}

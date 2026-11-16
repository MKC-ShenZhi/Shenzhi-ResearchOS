"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
    getKnowledgeClient,
    type KnowledgeTopic,
    type KnowledgeTopicListResponse,
} from "@/clients/knowledge";
import { TOPICS_QUERY_KEY } from "../topic-metadata";

export function topicDetailQueryKey(topicId: string) {
    return ["knowledge", "openalex-topic", topicId] as const;
}

export function useTopicDetail(topicId: string) {
    const queryClient = useQueryClient();
    const topicList =
        queryClient.getQueryData<KnowledgeTopicListResponse>(TOPICS_QUERY_KEY);
    const cachedTopic = topicList
        ? topicList.items.find((topic) => topic.id === topicId)
        : undefined;

    return useQuery<KnowledgeTopic>({
        queryKey: topicDetailQueryKey(topicId),
        queryFn: ({ signal }) => getKnowledgeClient().topic(topicId, signal),
        placeholderData: cachedTopic,
        enabled: Boolean(topicId),
    });
}

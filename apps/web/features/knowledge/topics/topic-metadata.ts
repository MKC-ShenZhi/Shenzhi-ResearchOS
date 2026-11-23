import type { KnowledgeTopic } from "@/clients/knowledge";

const FEATURED_TOPIC_IDS = ["openalex:topic:T10028", "openalex:topic:T11689"] as const;

export function selectFeaturedTopics(topics: readonly KnowledgeTopic[]): KnowledgeTopic[] {
    return FEATURED_TOPIC_IDS.flatMap((id) => {
        const topic = topics.find((item) => item.id === id && item.enabled !== false);
        return topic ? [topic] : [];
    });
}

function firstNonEmpty(...values: Array<string | null | undefined>): string {
    return values.map((value) => value?.trim()).find((value): value is string => Boolean(value)) ?? "";
}

export function resolveTopicDescription(topic: KnowledgeTopic): string {
    return firstNonEmpty(topic.descriptionDetail, topic.descriptionZh, topic.descriptionEn);
}

export const TOPICS_QUERY_KEY = ["knowledge", "openalex-topics"] as const;

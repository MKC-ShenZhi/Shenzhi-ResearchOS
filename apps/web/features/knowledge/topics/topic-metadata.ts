import type { KnowledgeTopic } from "@/clients/knowledge";

const FEATURED_TOPIC_IDS = ["reinforcement-learning", "deep-learning"] as const;

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

export function resolveSubjectQuery(topic: KnowledgeTopic): string {
    return firstNonEmpty(topic.subjectQuery, topic.nameEn, topic.nameZh);
}

export function toTopicMetadata(topic: KnowledgeTopic): KnowledgeTopic {
    return {
        ...topic,
        descriptionDetail: resolveTopicDescription(topic) || null,
        subjectQuery: resolveSubjectQuery(topic),
    };
}

export function findTopicMetadata(
    topics: readonly KnowledgeTopic[],
    topicId: string,
): KnowledgeTopic | undefined {
    const topic = topics.find((item) => item.id === topicId);
    return topic ? toTopicMetadata(topic) : undefined;
}

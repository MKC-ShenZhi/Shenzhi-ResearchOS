import type { KnowledgeTopic } from "@/clients/knowledge";

export interface TopicViewState { query: string; category: string; }

export function readTopicViewState(searchParams: URLSearchParams): TopicViewState {
  return { query: searchParams.get("q")?.trim() ?? "", category: searchParams.get("category")?.trim() ?? "" };
}

export function filterTopics(topics: KnowledgeTopic[], { query, category }: TopicViewState): KnowledgeTopic[] {
  const normalizedQuery = query.toLocaleLowerCase();
  return topics.filter((topic) => {
    if (category && topic.category !== category) return false;
    if (!normalizedQuery) return true;
    return [topic.nameZh, topic.nameEn, topic.descriptionZh, topic.descriptionEn, topic.author].join(" ").toLocaleLowerCase().includes(normalizedQuery);
  });
}

export function groupTopics(topics: KnowledgeTopic[]): Array<[string, KnowledgeTopic[]]> {
  const groups = new Map<string, KnowledgeTopic[]>();
  for (const topic of topics) groups.set(topic.category, [...(groups.get(topic.category) ?? []), topic]);
  return [...groups.entries()];
}


import type { KnowledgeTopic } from "@/clients/knowledge";

export interface TopicViewState { query: string; category: string; }

export function readTopicViewState(searchParams: URLSearchParams): TopicViewState {
  return { query: searchParams.get("q")?.trim() ?? "", category: searchParams.get("category")?.trim() ?? "" };
}

export function updateTopicViewParams(searchParams: URLSearchParams, next: Partial<TopicViewState>): URLSearchParams {
  const params = new URLSearchParams(searchParams);
  const state = { ...readTopicViewState(params), ...next };
  for (const [key, value] of [["q", state.query.trim()], ["category", state.category.trim()]]) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  return params;
}

export function filterTopics(topics: KnowledgeTopic[], { query, category }: TopicViewState): KnowledgeTopic[] {
  const normalizedQuery = query.trim().normalize("NFKC").toLocaleLowerCase();
  return topics.filter((topic) => {
    if (category && topic.category !== category) return false;
    if (!normalizedQuery) return true;
    const author = typeof topic.author === "string"
      ? topic.author
      : `${topic.author.id} ${topic.author.name}`;
    return [topic.id, topic.subjectQuery, topic.category, topic.nameZh, topic.nameEn, topic.descriptionZh, topic.descriptionEn, author]
      .join(" ")
      .normalize("NFKC")
      .toLocaleLowerCase()
      .includes(normalizedQuery);
  });
}

export function groupTopics(topics: KnowledgeTopic[]): Array<[string, KnowledgeTopic[]]> {
  const groups = new Map<string, KnowledgeTopic[]>();
  for (const topic of topics) {
    const group = groups.get(topic.category);
    if (group) group.push(topic);
    else groups.set(topic.category, [topic]);
  }
  return [...groups.entries()];
}


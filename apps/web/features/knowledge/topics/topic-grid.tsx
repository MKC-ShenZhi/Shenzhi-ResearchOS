import type { KnowledgeTopic } from "@/clients/knowledge";
import { TopicCard } from "./topic-card";

export function TopicGrid({ topics, featured = false }: { topics: KnowledgeTopic[]; featured?: boolean }) { return <div className={featured ? "grid gap-5 md:grid-cols-2" : "grid gap-5 md:grid-cols-2 xl:grid-cols-3"}>{topics.map((topic) => <TopicCard key={topic.id} topic={topic} featured={featured} />)}</div>; }


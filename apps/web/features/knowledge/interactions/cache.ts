import type { QueryClient } from "@tanstack/react-query";

export const INTERACTION_QUERY_KINDS = new Set([
  "paper-interaction", "topic-interaction", "my-likes", "my-collected-papers",
  "my-topic-follows", "collection-folder-papers",
  // Personal recommendation pages (and their request ids) belong to one account.
  "home-feed",
]);

/** Cancel old reads before refetching so a pre-write response cannot win. */
export async function refreshPaperQueries(client: QueryClient, userId: string, paperId?: string) {
  const filter = { predicate: (query: { queryKey: readonly unknown[] }) =>
    (query.queryKey[0] === "paper-interaction" && (!paperId || query.queryKey[2] === paperId))
    || (query.queryKey[0] === "my-likes" && query.queryKey[1] === userId) };
  await client.cancelQueries(filter);
  await client.invalidateQueries(filter);
}

export async function refreshCollectionQueries(client: QueryClient, userId: string, paperId?: string) {
  await Promise.all([
    refreshPaperQueries(client, userId, paperId),
    ...["my-collected-papers", "collection-folder-papers"].map(async (kind) => {
      const filter = { queryKey: [kind, userId] };
      await client.cancelQueries(filter);
      await client.invalidateQueries(filter);
    }),
  ]);
}

export async function refreshTopicQueries(client: QueryClient, userId: string, topicId: string) {
  const filter = { predicate: (query: { queryKey: readonly unknown[] }) =>
    (query.queryKey[0] === "topic-interaction" && query.queryKey[2] === topicId)
    || (query.queryKey[0] === "my-topic-follows" && query.queryKey[1] === userId) };
  await client.cancelQueries(filter);
  await client.invalidateQueries(filter);
}

export function clearOtherInteractionIdentities(client: QueryClient, userId: string) {
  client.removeQueries({ predicate: (query) => {
    if (!INTERACTION_QUERY_KINDS.has(String(query.queryKey[0]))) return false;
    const owner = query.queryKey[1];
    return typeof owner === "string" && owner !== "" && owner !== userId;
  } });
}

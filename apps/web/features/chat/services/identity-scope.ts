export type ChatIdentityScope = "anonymous" | `user:${string}`;

/** Browser-side Chat identity boundary, never a backend owner key. */
export function chatIdentityScope(userId: string | null | undefined): ChatIdentityScope {
  return userId ? `user:${userId}` : "anonymous";
}

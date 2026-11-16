"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/auth-provider";
import { PAPER_INTERACTION_CHANNEL, TOPIC_INTERACTION_CHANNEL } from "@/clients/backend/interactions";
import { clearOtherInteractionIdentities, refreshCollectionQueries, refreshPaperQueries, refreshTopicQueries } from "@/features/knowledge/interactions/cache";
import { useCollections } from "@/stores/collections";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? value as Record<string, unknown> : null;
}

/** Broadcasts are invalidation hints. Only the database supplies personal state. */
export function InteractionSync() {
  const { session, isPending } = useAuth();
  const userId = session?.user?.id ?? "";
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!isPending) clearOtherInteractionIdentities(queryClient, userId);
  }, [isPending, queryClient, userId]);

  useEffect(() => {
    if (isPending || typeof BroadcastChannel === "undefined") return;
    const paperChannel = new BroadcastChannel(PAPER_INTERACTION_CHANNEL);
    paperChannel.onmessage = (event: MessageEvent<unknown>) => {
      const message = asRecord(event.data);
      if (!message || typeof message.userId !== "string") return;
      const paperId = typeof message.paperId === "string" ? message.paperId : undefined;
      if (message.collectionsChanged === true) {
        void refreshCollectionQueries(queryClient, userId, paperId);
        if (message.userId === userId) void useCollections.getState().loadFolders().catch(() => {});
      } else if (paperId) {
        void refreshPaperQueries(queryClient, userId, paperId);
      }
    };
    const topicChannel = new BroadcastChannel(TOPIC_INTERACTION_CHANNEL);
    topicChannel.onmessage = (event: MessageEvent<unknown>) => {
      const message = asRecord(event.data);
      if (!message || typeof message.userId !== "string" || typeof message.topicId !== "string") return;
      void refreshTopicQueries(queryClient, userId, message.topicId);
    };
    return () => {
      paperChannel.close();
      topicChannel.close();
    };
  }, [isPending, queryClient, userId]);
  return null;
}

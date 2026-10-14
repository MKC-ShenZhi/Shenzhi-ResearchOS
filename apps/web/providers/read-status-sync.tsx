"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/auth-provider";
import { PAPER_READ_CHANNEL, paperReadStatusQueryKey, type PaperReadStatus } from "@/clients/backend/read-status";

/** Make a successful read in another browser tab visible without a refresh. */
export function ReadStatusSync() {
  const { session } = useAuth();
  const userId = session?.user?.id;
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!userId || typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(PAPER_READ_CHANNEL);
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const value = event.data;
      if (!value || typeof value !== "object") return;
      const message = value as Record<string, unknown>;
      if (message.userId !== userId || typeof message.paperId !== "string") return;
      if (message.status !== "read" && message.status !== "reading") return;
      queryClient.setQueryData<PaperReadStatus>(
        paperReadStatusQueryKey(userId, message.paperId),
        (current) => current === "read" ? "read" : message.status as PaperReadStatus,
      );
    };
    return () => channel.close();
  }, [queryClient, userId]);

  return null;
}

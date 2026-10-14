"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/auth-provider";
import { fetchPaperReadStatus, paperReadStatusQueryKey, type PaperReadStatus } from "@/clients/backend/read-status";

export function usePaperReadStatus(paperId: string, enabled = true): PaperReadStatus {
  const { session, isPending } = useAuth();
  const userId = session?.user?.id ?? "";
  const query = useQuery({
    queryKey: paperReadStatusQueryKey(userId, paperId),
    queryFn: () => fetchPaperReadStatus(userId, paperId),
    enabled: enabled && !isPending && Boolean(userId && paperId),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    refetchInterval: 10_000,
    retry: false,
  });
  return userId ? query.data ?? null : null;
}

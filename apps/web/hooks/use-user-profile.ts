"use client";

import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getUserProfile,
  patchUserProfile,
  type UserProfilePatch,
} from "@/clients/profile";
import { useAuth } from "@/components/auth/auth-provider";

const profileQueryKey = (userId: string | null) => ["user-profile", userId] as const;

export function useUserProfile() {
  const { session, isPending: sessionPending } = useAuth();
  const userId = session?.user.id ?? null;
  const queryClient = useQueryClient();
  const profileQuery = useQuery({
    queryKey: profileQueryKey(userId),
    queryFn: getUserProfile,
    enabled: !sessionPending && Boolean(userId),
  });
  const profileMutation = useMutation({
    mutationFn: ({ patch }: { userId: string; patch: UserProfilePatch }) =>
      patchUserProfile(patch),
    onSuccess: (updated, { userId: savedUserId }) => {
      queryClient.setQueryData(profileQueryKey(savedUserId), updated);
    },
  });

  const save = useCallback(
    async (patch: UserProfilePatch) => {
      if (!userId || profileMutation.isPending) return null;
      try {
        return await profileMutation.mutateAsync({ userId, patch });
      } catch {
        return null;
      }
    },
    [profileMutation, userId],
  );

  return {
    profile: userId ? (profileQuery.data ?? null) : null,
    loading: Boolean(userId) && profileQuery.isPending,
    saving: profileMutation.isPending,
    error: profileMutation.isError
      ? ("save" as const)
      : profileQuery.isError
        ? ("load" as const)
        : null,
    save,
  };
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getUserProfile, patchUserProfile, type UserProfile, type UserProfilePatch } from "@/clients/backend/profile";
import { useAuth } from "@/components/auth/auth-provider";

export function useUserProfile() {
  const { session, isPending } = useAuth();
  const userId = session?.user.id ?? null;
  const identityRef = useRef<string | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<"load" | "save" | null>(null);

  useEffect(() => {
    if (isPending) return;
    let cancelled = false;
    void Promise.resolve().then(async () => {
      identityRef.current = userId;
      setProfile(null);
      setError(null);
      if (!userId) {
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const value = await getUserProfile();
        if (!cancelled && identityRef.current === userId) setProfile(value);
      } catch {
        if (!cancelled && identityRef.current === userId) setError("load");
      } finally {
        if (!cancelled && identityRef.current === userId) setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [isPending, userId]);

  const save = useCallback(async (patch: UserProfilePatch) => {
    if (!userId || saving) return null;
    setSaving(true);
    setError(null);
    try {
      const updated = await patchUserProfile(patch);
      if (identityRef.current === userId) setProfile(updated);
      return updated;
    } catch {
      if (identityRef.current === userId) setError("save");
      return null;
    } finally {
      if (identityRef.current === userId) setSaving(false);
    }
  }, [saving, userId]);

  return { profile, loading, saving, error, save };
}

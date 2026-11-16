import type { AvatarKey, UserProfile } from "./types";

export const AVATAR_OPTIONS: ReadonlyArray<{ key: AvatarKey; src: string }> = [
  { key: "avatar-01", src: "/images/avatars/default/avatar-01.webp" },
  { key: "avatar-02", src: "/images/avatars/default/avatar-02.webp" },
  { key: "avatar-03", src: "/images/avatars/default/avatar-03.webp" },
  { key: "avatar-04", src: "/images/avatars/default/avatar-04.webp" },
  { key: "avatar-05", src: "/images/avatars/default/avatar-05.webp" },
];

export function avatarPath(key: string | null | undefined) {
  return AVATAR_OPTIONS.find((option) => option.key === key)?.src ?? null;
}

export function userAvatarSource(
  profile: Pick<UserProfile, "avatar_key" | "avatar_selected"> | null,
  authImage?: string | null,
) {
  const sessionAvatar = authImage?.trim() || null;
  if (!profile) return sessionAvatar;

  const profileAvatar = avatarPath(profile.avatar_key);
  return profile.avatar_selected ? profileAvatar : sessionAvatar || profileAvatar;
}

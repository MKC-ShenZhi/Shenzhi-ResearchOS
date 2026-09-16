import type { AvatarKey } from "@/clients/backend/profile";

export const AVATAR_OPTIONS: ReadonlyArray<{ key: AvatarKey; src: string }> = [
  { key: "avatar-01", src: "/images/avatars/default/avatar-01.webp" },
  { key: "avatar-02", src: "/images/avatars/default/avatar-02.webp" },
  { key: "avatar-03", src: "/images/avatars/default/avatar-03.webp" },
  { key: "avatar-04", src: "/images/avatars/default/avatar-04.webp" },
  { key: "avatar-05", src: "/images/avatars/default/avatar-05.webp" },
];

export function avatarPath(key: AvatarKey) {
  return AVATAR_OPTIONS.find((option) => option.key === key)?.src ?? AVATAR_OPTIONS[0].src;
}

import { apiJson } from "@/clients/backend/http";
import type { UserProfile, UserProfilePatch } from "./types";

export { AVATAR_OPTIONS, avatarPath, userAvatarSource } from "./avatar";

export type {
  Achievement,
  AvatarKey,
  EducationExperience,
  InstitutionExperience,
  UserProfile,
  UserProfilePatch,
} from "./types";

export function getUserProfile() {
  return apiJson<UserProfile>("/profile");
}

export function patchUserProfile(patch: UserProfilePatch) {
  return apiJson<UserProfile>("/profile", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

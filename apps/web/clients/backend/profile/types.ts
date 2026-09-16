export type AvatarKey =
  | "avatar-01"
  | "avatar-02"
  | "avatar-03"
  | "avatar-04"
  | "avatar-05";

export interface Achievement {
  title: string;
  detail: string;
  year: string | null;
}

export interface EducationExperience {
  institution: string;
  degree: string;
  field: string;
  start_year: string | null;
  end_year: string | null;
}

export interface InstitutionExperience {
  name: string;
  role: string;
  start_year: string | null;
  end_year: string | null;
}

export interface UserProfile {
  avatar_key: AvatarKey;
  avatar_selected: boolean;
  bio: string;
  achievements: Achievement[];
  educations: EducationExperience[];
  biography: string;
  institutions: InstitutionExperience[];
  created_at: string;
  updated_at: string;
}

export interface UserProfilePatch {
  avatar_key?: AvatarKey;
  bio?: string;
  achievements?: Achievement[];
  educations?: EducationExperience[];
  biography?: string;
  institutions?: InstitutionExperience[];
}

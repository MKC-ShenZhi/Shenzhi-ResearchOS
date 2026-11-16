"""Contracts for authenticated personal profiles and scholar portraits."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

AvatarKey = Annotated[str, StringConstraints(pattern=r'^avatar-0[1-5]$')]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
OptionalDetail = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Year = Annotated[str, StringConstraints(pattern=r'^\d{4}$')]


class Achievement(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: ShortText
    detail: OptionalDetail = ''
    year: Year | None = None


class EducationExperience(BaseModel):
    model_config = ConfigDict(extra='forbid')

    institution: ShortText
    degree: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ''
    field: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ''
    start_year: Year | None = None
    end_year: Year | None = None


class InstitutionExperience(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: ShortText
    role: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ''
    start_year: Year | None = None
    end_year: Year | None = None


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    avatar_key: AvatarKey
    avatar_selected: bool
    bio: str
    achievements: list[Achievement]
    educations: list[EducationExperience]
    biography: str
    institutions: list[InstitutionExperience]
    created_at: datetime
    updated_at: datetime


class UserProfilePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')

    avatar_key: AvatarKey | None = None
    bio: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    achievements: list[Achievement] | None = Field(default=None, max_length=20)
    educations: list[EducationExperience] | None = Field(default=None, max_length=20)
    biography: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = None
    institutions: list[InstitutionExperience] | None = Field(default=None, max_length=20)

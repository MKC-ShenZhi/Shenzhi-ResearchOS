"""Conference-deadline snapshot file and its public API contract."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CcfRank = Literal['A', 'B', 'C']
CoreRank = Literal['A*', 'A', 'B', 'C']
ThcplRank = Literal['A', 'B', 'C']
MilestoneKind = Literal['abstract', 'full']
DeadlineStatus = Literal['open', 'tbd', 'closed']


class ConferenceModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


# ---- Packaged snapshot (written by scripts/publish_conference_deadlines.py) ----

class SnapshotTimelineEntry(ConferenceModel):
    # Local wall-clock time `YYYY-MM-DD HH:MM:SS` in the edition timezone; None = TBD.
    abstract_deadline: str | None = None
    deadline: str | None = None
    comment: str | None = None


class SnapshotEdition(ConferenceModel):
    year: int
    link: str | None = None
    timezone: str
    date: str | None = None
    place: str | None = None
    timeline: list[SnapshotTimelineEntry] = Field(min_length=1)


class ConferenceRank(ConferenceModel):
    ccf: CcfRank | None = None
    core: CoreRank | None = None
    thcpl: ThcplRank | None = None


class SnapshotConference(ConferenceModel):
    id: str
    title: str
    description: str
    category: str
    dblp: str | None = None
    rank: ConferenceRank
    editions: list[SnapshotEdition] = Field(min_length=1)


class SnapshotCategory(ConferenceModel):
    id: str
    name: str
    name_en: str | None = None


class SnapshotSource(ConferenceModel):
    name: str
    url: str


class ConferenceSnapshotFile(ConferenceModel):
    schema_version: Literal[1]
    snapshot_id: str = Field(min_length=1)
    data_as_of: date
    source: SnapshotSource
    categories: list[SnapshotCategory] = Field(min_length=1)
    conferences: list[SnapshotConference]


# ---- Public contract ----

class ConferenceMilestone(ConferenceModel):
    kind: MilestoneKind
    # Absolute UTC instant; None means the organizers have not announced it yet.
    at: datetime | None
    # Official wall-clock time as published, in the edition timezone.
    local: str | None = None
    comment: str | None = None


class ConferenceEdition(ConferenceModel):
    year: int
    link: str | None = None
    timezone: str
    date: str | None = None
    place: str | None = None
    # Dated milestones in chronological order, then TBD milestones.
    milestones: list[ConferenceMilestone]


class ConferenceDeadline(ConferenceModel):
    id: str
    title: str
    description: str
    category: str
    dblp: str | None = None
    rank: ConferenceRank
    status: DeadlineStatus
    next_milestone: ConferenceMilestone | None = None
    last_deadline_at: datetime | None = None
    edition: ConferenceEdition
    edition_count: int = Field(ge=1)


class ConferenceDeadlineList(ConferenceModel):
    snapshot_id: str
    data_as_of: date
    source_url: str
    generated_at: datetime
    total: int = Field(ge=0)
    items: list[ConferenceDeadline]


class ConferenceCategory(ConferenceModel):
    id: str
    name: str
    name_en: str | None = None
    count: int = Field(ge=0)


class ConferenceCategoryList(ConferenceModel):
    snapshot_id: str
    items: list[ConferenceCategory]


class ConferenceFollowState(ConferenceModel):
    conference_id: str
    is_following: bool

"""ShenZhi's public contract for NSFC projects."""

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.schemas.knowledge import KnowledgeModel


class ProjectModel(KnowledgeModel):
    model_config = ConfigDict(alias_generator=to_camel)


class ProjectSummary(ProjectModel):
    award_number: str = Field(min_length=1)
    name: str = Field(min_length=1)
    award_year: int
    status: str
    program: str
    institutions: list[str]
    topics: list[str]
    summary: str = ''
    principal_investigators: list[str] = Field(default_factory=list)
    paper_count: int | None = Field(default=None, ge=0)


class ProjectList(ProjectModel):
    items: list[ProjectSummary]
    total: int = Field(ge=0)
    snapshot: bool


class ProjectMember(ProjectModel):
    name: str
    role: str


class ProjectPaper(ProjectModel):
    id: str
    title: str
    source_url: str | None


class ProjectDetail(ProjectSummary):
    start_date: str
    end_date: str
    source_url: str | None
    members: list[ProjectMember]
    papers: list[ProjectPaper]
    snapshot: bool

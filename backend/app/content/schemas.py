"""Shapes of portfolio content going in and out of the API."""

import re
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _url_or_empty(value: str) -> str:
    value = value.strip()
    if value and not re.match(r"^https://[^\s/$.?#].[^\s]*$", value):
        raise ValueError("must be a full https:// address")
    return value


def _month(value: str) -> str:
    if not MONTH.match(value):
        raise ValueError("must be a month written as YYYY-MM, e.g. 2024-07")
    return value


Text = Annotated[str, StringConstraints(strip_whitespace=True)]
Url = Annotated[str, StringConstraints(max_length=300), AfterValidator(_url_or_empty)]
Month = Annotated[str, AfterValidator(_month)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class FileRef(BaseModel):
    id: int
    filename: str
    content_type: str
    url: str


class ProfileIn(BaseModel):
    full_name: Annotated[Text, StringConstraints(min_length=1, max_length=120)]
    headline: Annotated[Text, StringConstraints(max_length=200)] = ""
    location: Annotated[Text, StringConstraints(max_length=120)] = ""
    summary_md: Annotated[str, StringConstraints(max_length=5_000)] = ""
    about_md: Annotated[str, StringConstraints(max_length=30_000)] = ""
    linkedin_url: Url = ""
    github_url: Url = ""
    photo_file_id: int | None = None
    cv_file_id: int | None = None


class ProfileOut(BaseModel):
    full_name: str
    headline: str
    location: str
    summary_md: str
    about_md: str
    linkedin_url: str
    github_url: str
    photo: FileRef | None
    cv: FileRef | None


class ExperienceIn(BaseModel):
    role: Annotated[Text, StringConstraints(min_length=1, max_length=200)]
    organisation: Annotated[Text, StringConstraints(min_length=1, max_length=200)]
    location: Annotated[Text, StringConstraints(max_length=120)] = ""
    start_month: Month
    end_month: Month | None = None
    description_md: Annotated[str, StringConstraints(max_length=10_000)] = ""

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_month is not None and self.end_month < self.start_month:
            raise ValueError("end_month must not be before start_month")
        return self


class ExperienceOut(ExperienceIn):
    id: int


class SkillGroupIn(BaseModel):
    name: Annotated[Text, StringConstraints(min_length=1, max_length=120)]
    items: list[Tag] = Field(default_factory=list, max_length=60)


class SkillGroupOut(SkillGroupIn):
    id: int


class ProjectIn(BaseModel):
    slug: Annotated[Text, StringConstraints(min_length=1, max_length=120)]
    title: Annotated[Text, StringConstraints(min_length=1, max_length=200)]
    summary: Annotated[Text, StringConstraints(max_length=500)] = ""
    body_md: Annotated[str, StringConstraints(max_length=100_000)] = ""
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    cover_file_id: int | None = None
    published: bool = False
    featured: bool = False

    @model_validator(mode="after")
    def _slug_format(self) -> Self:
        if not SLUG.match(self.slug):
            raise ValueError("slug must use lower-case letters, digits and single hyphens")
        return self


class ProjectSummaryOut(BaseModel):
    id: int
    slug: str
    title: str
    summary: str
    tags: list[str]
    cover: FileRef | None
    published: bool
    featured: bool


class ProjectOut(ProjectSummaryOut):
    body_md: str
    cover_file_id: int | None


class ReorderIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class PortfolioOut(BaseModel):
    """Everything a visitor can see, in one response."""

    profile: ProfileOut
    experience: list[ExperienceOut]
    skills: list[SkillGroupOut]
    projects: list[ProjectSummaryOut]


class ContactIn(BaseModel):
    name: Annotated[Text, StringConstraints(min_length=1, max_length=120)]
    email: Annotated[
        Text,
        StringConstraints(max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    ]
    subject: Annotated[Text, StringConstraints(min_length=1, max_length=200)]
    message: Annotated[Text, StringConstraints(min_length=10, max_length=5_000)]
    # Hidden field: people leave it empty, spam robots fill it in.
    website: Annotated[str, StringConstraints(max_length=300)] = ""

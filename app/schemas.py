from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class CourseOut(Schema):
    id: int
    title: str
    instructor: str
    blob_path: str | None = None
    total_hour: float | None = None
    description: str
    slug: str
    slug_part: str
    rate: float | None = None
    category: str
    badge: str | None = None
    language: str | None = None
    created_at: datetime
    is_expired: bool
    total_practice_test: int
    total_practice_test_questions: int
    is_practice_test: bool
    coupon_code: str | None = None

    @computed_field
    @property
    def image_url(self) -> str:
        return self.blob_path or "/static/placeholder.svg"


class CourseDetailOut(CourseOut):
    enroll_url: str | None = None
    moreinfo: str | None = None
    total_section: int | None = None
    udemy_id: str | None = None
    learn_who: list[str] = Field(default_factory=list)
    for_who: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    updated_at: datetime

    @field_validator("learn_who", "for_who", "requirements", mode="before")
    @classmethod
    def empty_lists(cls, value):
        return value or []


class PaginatedCourses(Schema):
    courses: list[CourseDetailOut]
    count: int
    page: int
    page_size: int = 15
    total_pages: int


class CategoryOut(Schema):
    name: str


class RefreshResult(Schema):
    message: str
    refreshed_at: datetime
    count: int
    total: int
    mode: Literal["page", "full"]


class SavedToggleOut(Schema):
    saved: bool
    course_id: int


class InfoOut(Schema):
    name: str
    upstream_base_url: str
    docs: str = "/api/docs"
    redoc: str = "/redoc"
    search_source: str = "local database"


class StatsOut(Schema):
    total: int
    upstream_total: int
    active: int
    practice_tests: int
    saved: int
    refreshed_at: str | None
    full_refreshed_at: str | None
    sync_state: str
    last_error: str | None

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(1000))
    instructor: Mapped[str] = mapped_column(String(500), default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    blob_path: Mapped[str | None] = mapped_column(String(500))
    total_hour: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")
    slug: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    slug_part: Mapped[str] = mapped_column(String(500), index=True)
    rate: Mapped[float | None] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(200), index=True, default="")
    badge: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=utcnow)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False)
    total_practice_test: Mapped[int] = mapped_column(Integer, default=0)
    total_practice_test_questions: Mapped[int] = mapped_column(Integer, default=0)
    is_practice_test: Mapped[bool] = mapped_column(Boolean, default=False)
    enroll_url: Mapped[str | None] = mapped_column(Text)
    coupon_code: Mapped[str | None] = mapped_column(String(500))
    moreinfo: Mapped[str | None] = mapped_column(Text)
    total_section: Mapped[int | None] = mapped_column(Integer)
    udemy_id: Mapped[str | None] = mapped_column(String(100))
    learn_who: Mapped[list | None] = mapped_column(JSON)
    for_who: Mapped[list | None] = mapped_column(JSON)
    requirements: Mapped[list | None] = mapped_column(JSON)
    detail_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SavedCourse(Base):
    __tablename__ = "saved_courses"
    __table_args__ = (UniqueConstraint("visitor_id", "course_id", name="uq_saved_visitor_course"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    visitor_id: Mapped[str] = mapped_column(String(64), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CatalogMeta(Base):
    __tablename__ = "catalog_meta"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

import asyncio
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
import logging
import math
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CatalogMeta, Course, SavedCourse, utcnow
from app.schemas import PaginatedCourses, RefreshResult, StatsOut
from app.services.coupon import extract_coupon_code, valid_enroll_url
from app.services.images import download_cover
from app.services.upstream import Upstream, UpstreamError

log = logging.getLogger(__name__)
PAGE_SIZE = 15


class RefreshThrottled(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Please wait {retry_after} seconds before refreshing the catalog again.")

# Udemy's 13 categories; upstream listCategories order still needs live verification.
CATEGORIES = (
    "Development", "Business", "Finance & Accounting", "IT & Software",
    "Office Productivity", "Personal Development", "Design", "Marketing",
    "Lifestyle", "Photography & Video", "Health & Fitness", "Music", "Teaching & Academics",
)


class SyncBusy(Exception):
    pass


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "li", "div", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "li", "div"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value) -> str:
    parser = TextParser()
    parser.feed(str(value or ""))
    return "\n".join(line.strip() for line in unescape("".join(parser.parts)).splitlines() if line.strip())


def flatten_text(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = plain_text(value)
        return [text] if text else []
    if isinstance(value, dict):
        for key in ("description", "text", "learnWho", "forWho", "requirement", "title", "name"):
            if key in value:
                return flatten_text(value[key])
        value = [item for key, item in value.items() if key.lower() not in {"id", "courseid", "createdat", "updatedat"}]
    if isinstance(value, list):
        return list(dict.fromkeys(text for item in value for text in flatten_text(item)))
    return []


class CourseData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=1000)
    slug: str = Field(min_length=1, max_length=1000)
    instructor: str = ""
    image_url: str = ""
    total_hour: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    rate: float | None = Field(default=None, ge=0, le=5, allow_inf_nan=False)
    category: str = Field(default="", max_length=200)
    badge: str | None = None
    language: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    is_expired: bool = False
    is_practice_test: bool = False
    total_practice_test: int = Field(default=0, ge=0)
    total_practice_test_questions: int = Field(default=0, ge=0)
    total_section: int | None = Field(default=None, ge=0)


def normalize_record(raw: dict, detail: bool = False) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Course must be an object")
    aliases = {
        "image_url": "imageUrl", "total_hour": "totalHour", "created_at": "createdAt",
        "is_expired": "isExpired", "is_practice_test": "isPracticeTest",
        "total_practice_test": "totalPracticeTest", "total_practice_test_questions": "totalPracticeTestQuestions",
        "total_section": "totalSection",
    }
    values = {}
    for key in CourseData.model_fields:
        source = aliases.get(key, key)
        if source in raw and raw[source] is not None:
            values[key] = raw[source]
    record = CourseData.model_validate(values).model_dump()
    record["slug"] = record["slug"].strip("/")
    record["slug_part"] = record["slug"].rsplit("/", 1)[-1]
    if not record["slug_part"]:
        raise ValueError("Empty course slug")
    created = record["created_at"]
    record["created_at"] = created.astimezone(timezone.utc).replace(tzinfo=None) if created.tzinfo else created
    record["description"] = plain_text(raw.get("description"))
    record["updated_at"] = utcnow()
    if detail:
        record.update(
            enroll_url=valid_enroll_url(raw.get("enrollUrl")),
            coupon_code=extract_coupon_code(raw.get("enrollUrl")),
            moreinfo=plain_text(raw.get("moreinfo")),
            udemy_id=str(raw["udemyId"]) if raw.get("udemyId") is not None else None,
            learn_who=flatten_text(raw.get("CourseLearnWho", raw.get("learnWho"))),
            for_who=flatten_text(raw.get("CourseForWho", raw.get("forWho"))),
            requirements=flatten_text(raw.get("requirements")),
            detail_fetched_at=utcnow(),
        )
    else:
        record.pop("total_section", None)
    return record


def meta(db: Session, key: str, default=None):
    row = db.get(CatalogMeta, key)
    return row.value if row else default


def set_meta(db: Session, key: str, value):
    row = db.get(CatalogMeta, key)
    if row is None:
        db.add(CatalogMeta(key=key, value=str(value), updated_at=utcnow()))
    else:
        row.value = str(value)
        row.updated_at = utcnow()


def acquire_lock(db: Session) -> str:
    token = str(uuid4())
    if db.get(CatalogMeta, "sync_lock") is None:
        try:
            db.add(CatalogMeta(key="sync_lock", value="", updated_at=datetime(2000, 1, 1)))
            db.commit()
        except IntegrityError:
            db.rollback()
    changed = db.execute(update(CatalogMeta).where(
        CatalogMeta.key == "sync_lock",
        CatalogMeta.updated_at < utcnow() - timedelta(minutes=10),
    ).values(value=token, updated_at=utcnow())).rowcount
    db.commit()
    if not changed:
        raise SyncBusy("A catalog sync is already running.")
    return token


def release_lock(db: Session, token: str):
    db.execute(update(CatalogMeta).where(CatalogMeta.key == "sync_lock", CatalogMeta.value == token).values(value="", updated_at=datetime(2000, 1, 1)))
    db.commit()


async def upsert_records(db: Session, upstream: Upstream, settings: Settings, records: list[dict], detail=False) -> int:
    values = []
    for raw in records:
        try:
            values.append(normalize_record(raw, detail=detail))
        except (ValidationError, ValueError, TypeError) as exc:
            raise UpstreamError("The catalog contains an invalid course record.") from exc
    semaphore = asyncio.Semaphore(4)

    async def cover(record):
        async with semaphore:
            return await download_cover(upstream.client, record["image_url"], record["id"], settings.blob_dir)

    covers = await asyncio.gather(*(cover(record) for record in values))
    for record, blob in zip(values, covers):
        existing = db.scalar(select(Course).where(or_(Course.id == record["id"], Course.slug == record["slug"])))
        if existing:
            record["id"] = existing.id
        # Keep the last local cover if a replacement download fails.
        record["blob_path"] = blob or (existing.blob_path if existing else None)
        insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
        statement = insert(Course).values(**record)
        statement = statement.on_conflict_do_update(index_elements=[Course.id], set_={key: value for key, value in record.items() if key != "id"})
        db.execute(statement)
    db.commit()
    db.expire_all()
    return len(values)


async def sync_catalog(db: Session, upstream: Upstream, settings: Settings, full: bool = False) -> RefreshResult:
    token = acquire_lock(db)
    processed, total = 0, 0
    try:
        last_attempt = meta(db, "refresh_attempted_at")
        cooldown = settings.refresh_cooldown_seconds
        if cooldown and last_attempt:
            remaining = cooldown - (utcnow() - datetime.fromisoformat(last_attempt)).total_seconds()
            if remaining > 0:
                raise RefreshThrottled(math.ceil(remaining))
        set_meta(db, "refresh_attempted_at", utcnow().isoformat())
        set_meta(db, "sync_state", "running")
        set_meta(db, "last_error", "")
        db.commit()
        for kind in ("practice", "courses"):
            page, seen = 1, set()
            while True:
                records, kind_total = await upstream.page(page, kind)
                ids = {str(row.get("id")) for row in records if isinstance(row, dict)}
                if full and ((not records and len(seen) < kind_total) or (records and ids.issubset(seen))):
                    raise UpstreamError("The source stopped pagination before the catalog was complete.")
                processed += await upsert_records(db, upstream, settings, records)
                seen.update(ids)
                set_meta(db, f"upstream_total:{kind}", kind_total)
                set_meta(db, "upstream_total", sum(int(meta(db, f"upstream_total:{name}", "0")) for name in ("practice", "courses")))
                set_meta(db, "sync_progress", processed)
                set_meta(db, "sync_lock", token)
                db.commit()
                if not full or len(seen) >= kind_total:
                    break
                page += 1
                if page > 10000:
                    raise UpstreamError("The upstream pagination safety limit was exceeded.")
            total += kind_total
        now = utcnow()
        set_meta(db, "refreshed_at", now.isoformat())
        if full:
            set_meta(db, "full_refreshed_at", now.isoformat())
        set_meta(db, "sync_state", "idle")
        db.commit()
        return RefreshResult(
            message=f"Refreshed {'full catalog' if full else 'page 1'} - {processed} courses, {total} total in the catalog",
            refreshed_at=now, count=processed, total=total, mode="full" if full else "page",
        )
    except RefreshThrottled:
        raise
    except Exception as exc:
        db.rollback()
        set_meta(db, "sync_state", "error")
        set_meta(db, "last_error", str(exc) if isinstance(exc, UpstreamError) else "Sync failed; the cached catalog is still available.")
        db.commit()
        raise
    finally:
        release_lock(db, token)


async def ensure_category(db: Session, upstream: Upstream, settings: Settings, category: str):
    key = f"category:{category}"
    stamp = meta(db, key)
    if stamp and datetime.fromisoformat(stamp) > utcnow() - timedelta(days=1):
        return
    token = acquire_lock(db)
    try:
        records = await upstream.category(category)
        # Commit small batches so an interrupted refresh retains useful cache data.
        for start in range(0, len(records), 15):
            await upsert_records(db, upstream, settings, records[start:start + 15], detail=True)
            set_meta(db, "sync_lock", token)
            db.commit()
        set_meta(db, key, utcnow().isoformat())
        db.commit()
    finally:
        release_lock(db, token)


async def ensure_detail(db: Session, upstream: Upstream, settings: Settings, course: Course) -> Course:
    if course.detail_fetched_at and course.detail_fetched_at > utcnow() - timedelta(hours=6):
        return course
    raw = await upstream.detail(course.slug_part)
    if str(raw["slug"]).strip("/").rsplit("/", 1)[-1] != course.slug_part:
        raise UpstreamError("The source details do not match the selected course.")
    course_id = course.id
    await upsert_records(db, upstream, settings, [raw], detail=True)
    return db.get(Course, course_id)


def find_course(db: Session, slug: str) -> Course | None:
    return db.scalar(select(Course).where(or_(Course.slug == slug.strip("/"), Course.slug_part == slug.rsplit("/", 1)[-1])).order_by(Course.created_at.desc()))


def query_courses(db: Session, *, page=1, q="", category=None, sort="latest", hide_expired=False, kind=None, visitor_id=None, saved_only=False) -> PaginatedCourses:
    if kind == "saved":
        saved_only, kind = True, None
    statement = select(Course)
    if saved_only:
        statement = statement.join(SavedCourse).where(SavedCourse.visitor_id == visitor_id)
    if q.strip():
        statement = statement.where(or_(*(column.icontains(q.strip(), autoescape=True) for column in (Course.title, Course.instructor, Course.description, Course.category))))
    if category:
        statement = statement.where(Course.category == category)
    if hide_expired:
        statement = statement.where(Course.is_expired.is_(False))
    if kind:
        statement = statement.where(Course.is_practice_test.is_(kind == "practice"))
    count = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    total_pages = max(1, math.ceil(count / PAGE_SIZE))
    page = min(page, total_pages)
    order = {"latest": Course.created_at.desc(), "rating": Course.rate.desc().nullslast(), "title": func.lower(Course.title).asc()}[sort]
    courses = db.scalars(statement.order_by(order, Course.id.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return PaginatedCourses(courses=courses, count=count, page=page, total_pages=total_pages)


def related_courses(db: Session, course: Course):
    return db.scalars(select(Course).where(Course.category == course.category, Course.id != course.id).order_by(Course.created_at.desc(), Course.id.desc()).limit(3)).all()


def saved_ids(db: Session, visitor_id: str) -> set[int]:
    return set(db.scalars(select(SavedCourse.course_id).where(SavedCourse.visitor_id == visitor_id)).all())


def catalog_stats(db: Session, visitor_id: str) -> StatsOut:
    total, active, practice_tests = db.execute(select(
        func.count(Course.id),
        func.count(Course.id).filter(Course.is_expired.is_(False)),
        func.count(Course.id).filter(Course.is_practice_test.is_(True)),
    )).one()
    metadata = dict(db.execute(select(CatalogMeta.key, CatalogMeta.value).where(CatalogMeta.key.in_(
        ("upstream_total", "refreshed_at", "full_refreshed_at", "sync_state", "last_error"),
    ))).all())
    return StatsOut(
        total=total, upstream_total=int(metadata.get("upstream_total", "0")),
        active=active, practice_tests=practice_tests,
        saved=db.scalar(select(func.count(SavedCourse.id)).where(SavedCourse.visitor_id == visitor_id)) or 0,
        refreshed_at=metadata.get("refreshed_at"), full_refreshed_at=metadata.get("full_refreshed_at"),
        sync_state=metadata.get("sync_state", "idle"), last_error=metadata.get("last_error") or None,
    )

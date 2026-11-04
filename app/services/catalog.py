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
from starlette.concurrency import run_in_threadpool

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
    await run_in_threadpool(_store_records, db, values, covers)
    return len(values)


def _store_records(db: Session, values: list[dict], covers: list[str | None]):
    if not values:
        db.commit()
        db.expire_all()
        return
    rows = db.execute(select(Course.id, Course.slug, Course.blob_path).where(or_(
        Course.id.in_([record["id"] for record in values]),
        Course.slug.in_([record["slug"] for record in values]),
    ))).mappings().all()
    by_id = {row["id"]: row for row in rows}
    by_slug = {row["slug"]: row for row in rows}
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    for record, blob in zip(values, covers):
        id_match = by_id.get(record["id"])
        slug_match = by_slug.get(record["slug"])
        existing = id_match or slug_match
        if id_match and slug_match and id_match["id"] != slug_match["id"]:
            # Preserve the database's match order for conflicting source identities.
            existing = db.execute(select(Course.id, Course.slug, Course.blob_path).where(or_(
                Course.id == record["id"], Course.slug == record["slug"],
            ))).mappings().first()
        if existing:
            record["id"] = existing["id"]
        # Keep the last local cover if a replacement download fails.
        record["blob_path"] = blob or (existing["blob_path"] if existing else None)
        statement = insert(Course).values(**record)
        statement = statement.on_conflict_do_update(index_elements=[Course.id], set_={key: value for key, value in record.items() if key != "id"})
        db.execute(statement)
        if existing:
            by_slug.pop(existing["slug"], None)
        stored = {key: record[key] for key in ("id", "slug", "blob_path")}
        by_id[stored["id"]] = by_slug[stored["slug"]] = stored
    db.commit()
    db.expire_all()


def _commit_meta(db: Session, values: dict):
    for key, value in values.items():
        set_meta(db, key, value)
    db.commit()


def _start_sync(db: Session, cooldown: int):
    last_attempt = meta(db, "refresh_attempted_at")
    if cooldown and last_attempt:
        remaining = cooldown - (utcnow() - datetime.fromisoformat(last_attempt)).total_seconds()
        if remaining > 0:
            raise RefreshThrottled(math.ceil(remaining))
    _commit_meta(db, {"refresh_attempted_at": utcnow().isoformat(), "sync_state": "running", "last_error": ""})


def _sync_progress(db: Session, kind: str, total: int, processed: int, token: str):
    set_meta(db, f"upstream_total:{kind}", total)
    _commit_meta(db, {
        "upstream_total": sum(int(meta(db, f"upstream_total:{name}", "0")) for name in ("practice", "courses")),
        "sync_progress": processed, "sync_lock": token,
    })


def _sync_failed(db: Session, exc: Exception):
    db.rollback()
    _commit_meta(db, {
        "sync_state": "error",
        "last_error": str(exc) if isinstance(exc, UpstreamError) else "Sync failed; the cached catalog is still available.",
    })


async def sync_catalog(db: Session, upstream: Upstream, settings: Settings, full: bool = False) -> RefreshResult:
    token = await run_in_threadpool(acquire_lock, db)
    processed, total = 0, 0
    try:
        await run_in_threadpool(_start_sync, db, settings.refresh_cooldown_seconds)
        for kind in ("practice", "courses"):
            page, seen = 1, set()
            while True:
                records, kind_total = await upstream.page(page, kind)
                ids = {str(row.get("id")) for row in records if isinstance(row, dict)}
                if full and ((not records and len(seen) < kind_total) or (records and ids.issubset(seen))):
                    raise UpstreamError("The source stopped pagination before the catalog was complete.")
                processed += await upsert_records(db, upstream, settings, records)
                seen.update(ids)
                await run_in_threadpool(_sync_progress, db, kind, kind_total, processed, token)
                if not full or len(seen) >= kind_total:
                    break
                page += 1
                if page > 10000:
                    raise UpstreamError("The upstream pagination safety limit was exceeded.")
            total += kind_total
        now = utcnow()
        metadata = {"refreshed_at": now.isoformat(), "sync_state": "idle"}
        if full:
            metadata["full_refreshed_at"] = now.isoformat()
        await run_in_threadpool(_commit_meta, db, metadata)
        return RefreshResult(
            message=f"Refreshed {'full catalog' if full else 'page 1'} - {processed} courses, {total} total in the catalog",
            refreshed_at=now, count=processed, total=total, mode="full" if full else "page",
        )
    except RefreshThrottled:
        raise
    except Exception as exc:
        await run_in_threadpool(_sync_failed, db, exc)
        raise
    finally:
        await run_in_threadpool(release_lock, db, token)


async def ensure_category(db: Session, upstream: Upstream, settings: Settings, category: str):
    key = f"category:{category}"
    stamp = await run_in_threadpool(meta, db, key)
    if stamp and datetime.fromisoformat(stamp) > utcnow() - timedelta(days=1):
        return
    token = await run_in_threadpool(acquire_lock, db)
    try:
        records = await upstream.category(category)
        # Commit small batches so an interrupted refresh retains useful cache data.
        for start in range(0, len(records), 15):
            await upsert_records(db, upstream, settings, records[start:start + 15], detail=True)
            await run_in_threadpool(_commit_meta, db, {"sync_lock": token})
        await run_in_threadpool(_commit_meta, db, {key: utcnow().isoformat()})
    finally:
        await run_in_threadpool(release_lock, db, token)


async def ensure_detail(db: Session, upstream: Upstream, settings: Settings, course: Course) -> Course:
    if course.detail_fetched_at and course.detail_fetched_at > utcnow() - timedelta(hours=6):
        return course
    raw = await upstream.detail(course.slug_part)
    if str(raw["slug"]).strip("/").rsplit("/", 1)[-1] != course.slug_part:
        raise UpstreamError("The source details do not match the selected course.")
    course_id = course.id
    await upsert_records(db, upstream, settings, [raw], detail=True)
    return await run_in_threadpool(db.get, Course, course_id)


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


# Function words that betray a non-English listing even when upstream reports "English".
_NON_ENGLISH_WORDS = frozenset({
    "und", "der", "die", "das", "für", "mit", "ohne", "dich", "dein", "eine", "einen", "nicht",
    "le", "les", "des", "une", "pour", "dans", "avec", "sur", "aux", "est", "vous",
    "los", "las", "para", "con", "por", "una", "del", "como",
})

# "… (Arabic Language)" style listings belong in the catalogue, not the English-language shelf.
_FOREIGN_LANGUAGE_TAGS = ("arabic", "german", "french", "spanish", "hindi", "portuguese", "italian",
                          "polish", "turkish", "urdu", "vietnamese", "tamil", "malay", "indonesian")


def _readable_listing(course: Course) -> bool:
    title = course.title or ""
    if not title.isascii() or not 12 <= len(title) <= 80:
        return False
    lowered = title.lower()
    if any(tag in lowered for tag in _FOREIGN_LANGUAGE_TAGS):
        return False
    words = [word.strip(".,:;!?()[]'\"").lower() for word in title.split()]
    return sum(word in _NON_ENGLISH_WORDS for word in words) < 2


def landing_featured(db: Session, *, limit: int = 4) -> list[Course]:
    """Shelf-worthy courses: newest readable English listings, one per instructor."""
    candidates = db.scalars(
        select(Course)
        .where(Course.is_expired.is_(False), Course.is_practice_test.is_(False),
               Course.language == "English", Course.blob_path.is_not(None))
        .order_by(Course.created_at.desc(), Course.id.desc())
        .limit(300)
    ).all()
    featured, instructors = [], set()
    for course in candidates:
        if course.instructor in instructors or not _readable_listing(course):
            continue
        featured.append(course)
        instructors.add(course.instructor)
        if len(featured) == limit:
            break
    if featured:
        rated = max(featured, key=lambda course: course.rate or 0)
        if (rated.rate or 0) > 0 and rated is not featured[0]:
            featured.remove(rated)
            featured.insert(0, rated)
    return featured


def category_counts(db: Session) -> list[tuple[str, int]]:
    """Courses per category, largest first. Empty categories sink to the end."""
    counted = dict(db.execute(
        select(Course.category, func.count(Course.id))
        .where(Course.is_practice_test.is_(False), Course.category.is_not(None))
        .group_by(Course.category)
    ).all())
    return sorted(((name, counted.get(name, 0)) for name in CATEGORIES), key=lambda item: item[1], reverse=True)


def related_courses(db: Session, course: Course):
    return db.scalars(select(Course).where(Course.category == course.category, Course.id != course.id).order_by(Course.created_at.desc(), Course.id.desc()).limit(3)).all()


def saved_ids(db: Session, visitor_id: str) -> set[int]:
    return set(db.scalars(select(SavedCourse.course_id).where(SavedCourse.visitor_id == visitor_id)).all())


def catalog_stats(db: Session, visitor_id: str) -> StatsOut:
    total, active, courses, practice_tests = db.execute(select(
        func.count(Course.id),
        func.count(Course.id).filter(Course.is_expired.is_(False)),
        func.count(Course.id).filter(Course.is_practice_test.is_(False)),
        func.count(Course.id).filter(Course.is_practice_test.is_(True)),
    )).one()
    metadata = dict(db.execute(select(CatalogMeta.key, CatalogMeta.value).where(CatalogMeta.key.in_(
        ("upstream_total", "refreshed_at", "full_refreshed_at", "sync_state", "last_error"),
    ))).all())
    return StatsOut(
        total=total, upstream_total=int(metadata.get("upstream_total", "0")),
        active=active, courses=courses, practice_tests=practice_tests,
        saved=db.scalar(select(func.count(SavedCourse.id)).where(SavedCourse.visitor_id == visitor_id)) or 0,
        refreshed_at=metadata.get("refreshed_at"), full_refreshed_at=metadata.get("full_refreshed_at"),
        sync_state=metadata.get("sync_state", "idle"), last_error=metadata.get("last_error") or None,
    )

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import Course, SavedCourse
from app.routers.dependencies import DB, Filters, Remote
from app.schemas import CategoryOut, CourseDetailOut, CourseOut, InfoOut, PaginatedCourses, SavedToggleOut, StatsOut
from app.services import catalog

router = APIRouter(prefix="/api", tags=["Catalog"])


async def course_list(db, upstream, params, visitor_id):
    if params["category"] and params["kind"] != "saved":
        await catalog.ensure_category(db, upstream, get_settings(), params["category"])
    return catalog.query_courses(db, **params, visitor_id=visitor_id)


@router.get("/courses", response_model=PaginatedCourses)
async def courses(request: Request, db: DB, upstream: Remote, params: Filters):
    return await course_list(db, upstream, params, request.state.visitor_id)


@router.get("/courses/search", response_model=PaginatedCourses)
async def search(request: Request, db: DB, upstream: Remote, params: Filters):
    return await course_list(db, upstream, params, request.state.visitor_id)


@router.get("/categories", response_model=list[CategoryOut])
def categories():
    return [CategoryOut(name=name) for name in catalog.CATEGORIES]


@router.get("/info", response_model=InfoOut)
def info():
    settings = get_settings()
    return InfoOut(name=settings.app_name, upstream_base_url=str(settings.upstream_api_base))


@router.get("/stats", response_model=StatsOut)
def stats(request: Request, db: DB):
    return catalog.catalog_stats(db, request.state.visitor_id)


@router.get("/saved", response_model=list[CourseOut])
def saved(request: Request, db: DB):
    return db.scalars(select(Course).join(SavedCourse).where(SavedCourse.visitor_id == request.state.visitor_id).order_by(SavedCourse.created_at.desc())).all()


@router.post("/saved/{course_id}/toggle", response_model=SavedToggleOut)
def toggle_saved(course_id: int, request: Request, db: DB):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "Course not found.")
    existing = db.scalar(select(SavedCourse).where(SavedCourse.course_id == course_id, SavedCourse.visitor_id == request.state.visitor_id))
    if existing:
        db.delete(existing)
    else:
        db.add(SavedCourse(course_id=course_id, visitor_id=request.state.visitor_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "The bookmark changed in another tab. Reload the page.")
    return SavedToggleOut(saved=existing is None, course_id=course_id)


@router.get("/courses/{slug_part}/related", response_model=list[CourseOut])
def related(slug_part: str, db: DB):
    course = catalog.find_course(db, slug_part)
    if course is None:
        raise HTTPException(404, "Course not found.")
    return catalog.related_courses(db, course)


@router.get("/courses/{slug_part}", response_model=CourseDetailOut)
async def detail(slug_part: str, db: DB, upstream: Remote):
    course = catalog.find_course(db, slug_part)
    if course is None:
        raise HTTPException(404, "Course not found in the local catalog.")
    return await catalog.ensure_detail(db, upstream, get_settings(), course)

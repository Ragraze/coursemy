from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.config import ROOT, get_settings
from app.routers.dependencies import DB, Filters, Remote
from app.services import catalog
from app.services.upstream import UpstreamError

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=ROOT / "app/templates")
templates.env.filters["urlquote"] = lambda value: quote(str(value), safe="")


def context(request, db, **values):
    return dict(request=request, app_name=get_settings().app_name, stats=catalog.catalog_stats(db, request.state.visitor_id),
                saved_ids=catalog.saved_ids(db, request.state.visitor_id), categories=catalog.CATEGORIES, **values)


async def render_catalog(request, db, upstream, params):
    params = {**params, "kind": params["kind"] or "courses"}
    saved_only = params["kind"] == "saved"
    error = None
    if params["category"] and not saved_only:
        try:
            await catalog.ensure_category(db, upstream, get_settings(), params["category"])
        except (UpstreamError, catalog.SyncBusy) as exc:
            error = str(exc)
    result = catalog.query_courses(db, **params, visitor_id=request.state.visitor_id, saved_only=saved_only)
    path = "/courses"

    def page_url(page):
        return path + "?" + urlencode({**{k: v for k, v in params.items() if v not in (None, "", False)}, "page": page})

    values = context(request, db, result=result, filters=params, saved_only=saved_only, error=error,
                     page_url=page_url, page_numbers=sorted({1, result.total_pages, *range(max(1, result.page - 2), min(result.total_pages, result.page + 2) + 1)}))
    partial = request.headers.get("HX-Request") == "true" and request.headers.get("HX-History-Restore-Request") != "true"
    template = "partials/results.html" if partial else "index.html"
    response = templates.TemplateResponse(request=request, name=template, context=values)
    response.headers["Vary"] = "HX-Request, HX-History-Restore-Request, Cookie"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/")
def landing(request: Request, db: DB):
    candidates = catalog.query_courses(db, hide_expired=True, kind="courses").courses
    featured = []
    instructors = set()
    for course in candidates:
        if course.instructor not in instructors:
            featured.append(course)
            instructors.add(course.instructor)
        if len(featured) == 6:
            break
    return templates.TemplateResponse(request=request, name="landing.html", context=context(request, db, featured=featured), headers={"Cache-Control": "private, no-store"})


@router.get("/courses")
async def index(request: Request, db: DB, upstream: Remote, params: Filters):
    return await render_catalog(request, db, upstream, params)


@router.get("/course/{slug:path}")
async def detail(slug: str, request: Request, db: DB, upstream: Remote):
    course = catalog.find_course(db, slug)
    if course is None:
        return templates.TemplateResponse(request=request, name="error.html", context=context(request, db, message="Course not found in the local catalog."), status_code=404)
    error = None
    try:
        course = await catalog.ensure_detail(db, upstream, get_settings(), course)
    except UpstreamError as exc:
        error = str(exc)
    return templates.TemplateResponse(request=request, name="course_detail.html", context=context(
        request, db, course=course, related=catalog.related_courses(db, course), error=error,
        coupon_fresh=course.detail_fetched_at is not None and error is None,
    ), headers={"Cache-Control": "private, no-store"})

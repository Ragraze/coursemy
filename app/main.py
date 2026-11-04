import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import re
import secrets
from urllib.parse import urlsplit

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
from sqlalchemy import inspect
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import ROOT, get_settings
from app.database import SessionLocal, engine
from app.routers import admin, courses, pages
from app.services.catalog import RefreshThrottled, SyncBusy, meta, sync_catalog
from app.services.upstream import Upstream, UpstreamError

log = logging.getLogger(__name__)


async def full_sync():
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15, limits=httpx.Limits(max_connections=8)) as client:
        with SessionLocal() as db:
            try:
                await sync_catalog(db, Upstream(client, str(settings.upstream_api_base)), settings, full=True)
            except (SyncBusy, RefreshThrottled) as exc:
                log.info("Catalog sync skipped: %s", exc)
            except Exception:
                log.exception("Catalog sync failed; serving the persisted cache")


def scheduled_sync():
    asyncio.run(full_sync())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not inspect(engine).has_table("courses"):
        raise RuntimeError("Database migrations have not been applied. Run: alembic upgrade head")
    settings.blob_dir.mkdir(parents=True, exist_ok=True)
    scheduler = None
    initial_task = None
    async with httpx.AsyncClient(timeout=15, limits=httpx.Limits(max_connections=8)) as client:
        app.state.upstream = Upstream(client, str(settings.upstream_api_base))
        if settings.scheduler_enabled:
            scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
            scheduler.add_job(scheduled_sync, "cron", minute="0,15,30,45", id="catalog", max_instances=1, coalesce=True, misfire_grace_time=1800)
            scheduler.start()
        if settings.initial_sync_enabled:
            with SessionLocal() as db:
                if not meta(db, "full_refreshed_at"):
                    initial_task = asyncio.create_task(full_sync())
        try:
            yield
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)
            if initial_task:
                initial_task.cancel()
                with suppress(asyncio.CancelledError):
                    await initial_task


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan, docs_url="/api/docs")
    settings.blob_dir.mkdir(parents=True, exist_ok=True)
    application.mount("/static/blobs", StaticFiles(directory=settings.blob_dir), name="blobs")
    application.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")

    def invalid_search(request):
        return pages.templates.TemplateResponse(request=request, name="error.html", context={
            "app_name": settings.app_name, "error_title": "Invalid search",
            "message": "Use up to 300 characters without control characters, a valid category, sort order, course type, and a positive page number.",
        }, status_code=422, headers={"Cache-Control": "private, no-store"})

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path == "/courses":
            return invalid_search(request)
        return await request_validation_exception_handler(request, exc)

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        if request.url.path == "/courses" and exc.status_code == 422:
            return invalid_search(request)
        return await http_exception_handler(request, exc)

    @application.middleware("http")
    async def visitor(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if request.headers.get("sec-fetch-site") == "cross-site" or (origin and urlsplit(origin).netloc != urlsplit(str(request.url)).netloc):
                return JSONResponse({"detail": "Cross-site request rejected."}, status_code=403)
        visitor_id = request.cookies.get("course_visitor", "")
        fresh = not re.fullmatch(r"[A-Za-z0-9_-]{43}", visitor_id)
        request.state.visitor_id = secrets.token_urlsafe(32) if fresh else visitor_id
        response = await call_next(request)
        if fresh:
            response.set_cookie("course_visitor", request.state.visitor_id, max_age=365 * 86400, httponly=True, secure=settings.cookie_secure, samesite="lax")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/saved") or request.url.path == "/api/stats" or (request.url.path.startswith("/api/courses") and request.query_params.get("kind") == "saved"):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Vary"] = "Cookie"
        return response

    @application.exception_handler(UpstreamError)
    async def upstream_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @application.exception_handler(SyncBusy)
    async def sync_busy(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409, headers={"Retry-After": "30"})

    @application.exception_handler(RefreshThrottled)
    async def refresh_throttled(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=429, headers={"Retry-After": str(exc.retry_after)})

    application.include_router(courses.router)
    application.include_router(admin.router)
    application.include_router(pages.router)
    return application


app = create_app()

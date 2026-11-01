from fastapi import APIRouter

from app.config import get_settings
from app.routers.dependencies import DB, Remote
from app.schemas import RefreshResult
from app.services.catalog import sync_catalog

router = APIRouter(prefix="/api/catalog", tags=["Administration"])


@router.post("/refresh", response_model=RefreshResult)
@router.post("/refreshCourses", response_model=RefreshResult, deprecated=True)
async def refresh(db: DB, upstream: Remote, full: bool = False):
    return await sync_catalog(db, upstream, get_settings(), full=full)

from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.catalog import CATEGORIES
from app.services.upstream import Upstream

DB = Annotated[Session, Depends(get_db)]


def get_upstream(request: Request) -> Upstream:
    return request.app.state.upstream


Remote = Annotated[Upstream, Depends(get_upstream)]


def filters(
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    q: Annotated[str, Query(max_length=300, pattern=r"^[^\x00-\x1f\x7f]*$")] = "",
    category: Annotated[str | None, Query(max_length=200)] = None,
    sort: Literal["latest", "rating", "title"] = "latest",
    hide_expired: bool = False,
    kind: Literal["courses", "practice", "saved"] | None = None,
):
    if category and category not in CATEGORIES:
        raise HTTPException(422, "Unknown category.")
    return dict(page=page, q=q.strip(), category=category or None, sort=sort, hide_expired=hide_expired, kind=kind)


Filters = Annotated[dict, Depends(filters)]

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)


class UpstreamError(Exception):
    pass


class Upstream:
    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def get(self, path: str, **params):
        for attempt in range(3):
            try:
                response = await self.client.get(f"{self.base_url}/{path.lstrip('/')}", params=params, timeout=15)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500 or exc.response.status_code == 429
                if not retryable or attempt == 2:
                    log.warning("Upstream request failed: %s (%s)", path, type(exc).__name__)
                    raise UpstreamError("The course source is unavailable. Please try again later.") from exc
                await asyncio.sleep(0.5 * (2 ** attempt))

    async def page(self, page: int, kind: str = "courses"):
        params = {"page": page}
        if kind == "practice":
            params["type"] = "practice-test"
        data = await self.get("course", **params)
        if not isinstance(data, dict) or not isinstance(data.get("Course"), list) or not isinstance(data.get("count"), int) or data["count"] < 0:
            raise UpstreamError("The upstream catalog format has changed.")
        return data["Course"], data["count"]

    async def detail(self, slug_part: str):
        data = await self.get("course/detail", slug=slug_part)
        if isinstance(data, dict) and isinstance(data.get("Course"), (list, dict)):
            data = data["Course"]
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict) or not data.get("id") or not data.get("slug"):
            raise UpstreamError("Course details are unavailable from the source.")
        return data

    async def category(self, category: str):
        data = await self.get("course/detail/category", category=category)
        if isinstance(data, dict):
            data = data.get("Course", data.get("courses"))
        if not isinstance(data, list):
            raise UpstreamError("The upstream category format has changed.")
        return data

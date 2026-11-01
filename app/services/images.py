import asyncio
from io import BytesIO
import logging
from pathlib import Path
import secrets
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)
MAX_BYTES = 8 * 1024 * 1024
ALLOWED_HOSTS = {"img-c.udemycdn.com", "img-b.udemycdn.com", "img-a.udemycdn.com"}


def resize_cover(data: bytes, target: Path):
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 25_000_000:
            raise ValueError("Image dimensions exceed limit")
        source = ImageOps.exif_transpose(source).convert("RGB")
        cover = ImageOps.fit(source, (640, 360), method=Image.Resampling.LANCZOS)
        temporary = target.with_suffix(f".{secrets.token_hex(4)}.tmp")
        try:
            cover.save(temporary, format="JPEG", quality=85, optimize=True)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


async def download_cover(client: httpx.AsyncClient, image_url: str, course_id: int, blob_dir: Path) -> str | None:
    target = blob_dir / f"{int(course_id)}.jpg"
    if target.is_file():
        return f"/static/blobs/{int(course_id)}.jpg"
    try:
        parsed = urlsplit(image_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.port not in (None, 443):
            raise ValueError("Image host is not an allowed Udemy CDN")
        async with client.stream("GET", image_url, timeout=15, follow_redirects=False) as response:
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError("Image exceeds size limit")
        blob_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(resize_cover, bytes(data), target)
        return f"/static/blobs/{int(course_id)}.jpg"
    except (httpx.HTTPError, OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        log.warning("Cover unavailable for course %s; using placeholder", course_id)
        return None

import asyncio
from datetime import timedelta

import httpx
from PIL import Image
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Course, utcnow
from app.services.catalog import (SyncBusy, acquire_lock, ensure_detail, flatten_text, normalize_record,
                                  plain_text, query_courses, release_lock, sync_catalog, upsert_records)
from app.services.images import download_cover
from app.services.upstream import Upstream, UpstreamError
from tests.conftest import record


def test_full_refresh_is_persisted_and_idempotent(database, remote):
    with database() as db:
        result = asyncio.run(sync_catalog(db, remote[0], get_settings(), full=True))
        assert result.count == result.total == 16
        asyncio.run(sync_catalog(db, remote[0], get_settings(), full=True))
        assert db.scalar(select(func.count(Course.id))) == 16
    with database() as reopened:
        assert reopened.get(Course, 16).slug_part == "python-course-16"
        path = get_settings().blob_dir / "1.jpg"
        with Image.open(path) as cover:
            assert cover.size == (640, 360)


def test_local_search_filters_sort_and_pagination(populated, database, remote):
    request_count = len(remote[1])
    with database() as db:
        assert query_courses(db, q="SQL").count == 16
        assert query_courses(db, q="fixture instructor").count == 16
        assert query_courses(db, q="Business").count == 8
        assert query_courses(db, q="Python", category="Development", hide_expired=True).count == 7
        assert query_courses(db, kind="practice").courses[0].id == 3
        assert query_courses(db, kind="courses").count == 15
        assert len(query_courses(db, page=2).courses) == 1
        assert query_courses(db, sort="title").courses[0].id == 1
        assert query_courses(db, sort="rating").courses[0].rate == 4.9
    assert len(remote[1]) == request_count


def test_list_refresh_preserves_existing_detail(populated, database, remote):
    with database() as db:
        course = asyncio.run(ensure_detail(db, remote[0], get_settings(), db.get(Course, 1)))
        assert course.coupon_code == "TEST-1"
        assert course.learn_who == ["Build an API"]
        asyncio.run(sync_catalog(db, remote[0], get_settings()))
        db.refresh(course)
        assert course.coupon_code == "TEST-1"
        assert course.total_section == 6


def test_refresh_lock_blocks_another_process_and_recovers(database):
    with database() as first, database() as second:
        token = acquire_lock(first)
        with pytest.raises(SyncBusy):
            acquire_lock(second)
        release_lock(first, token)
        release_lock(second, acquire_lock(second))


def test_nested_text_and_html_are_plain():
    assert plain_text("<p>Hello &amp; welcome</p><script>bad()</script><p>Next</p>") == "Hello & welcome\nNext"
    assert flatten_text([{"id": 1, "learnWho": {"description": "<b>Build</b>"}}, "Build"]) == ["Build"]
    normalized = normalize_record(record(1, detail=True), detail=True)
    assert normalized["udemy_id"] == "1001"
    assert normalized["moreinfo"] == "Useful details"
    assert normalized["for_who"] == ["Python learners"]


def test_upstream_retries_exactly_twice():
    attempts = []

    def fail(request):
        attempts.append(request)
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            with pytest.raises(UpstreamError):
                await Upstream(client, "https://example.test/api").page(1)
    asyncio.run(run())
    assert len(attempts) == 3


def test_broken_pagination_does_not_claim_full_sync(database, remote):
    upstream = remote[0]
    original = upstream.page

    async def repeating(page, kind="courses"):
        return await original(1, kind)

    upstream.page = repeating
    with database() as db:
        with pytest.raises(UpstreamError):
            asyncio.run(sync_catalog(db, upstream, get_settings(), full=True))
        assert db.get(Course, 1) is not None


def test_image_failure_uses_placeholder_and_blocks_private_hosts(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"not-an-image")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await download_cover(client, "http://127.0.0.1/private", 1, tmp_path) is None
            assert not calls
            assert await download_cover(client, "https://img-c.udemycdn.com/broken.jpg", 1, tmp_path) is None
    asyncio.run(run())
    assert not (tmp_path / "1.jpg").exists()


def test_refresh_imports_all_practice_pages_and_keeps_types_separate(database, remote):
    class PracticeSource(Upstream):
        async def get(self, path, **params):
            if path == "course" and params.get("type") == "practice-test":
                page = params["page"]
                records = []
                for number in (range(1, 16) if page == 1 else range(16, 17)):
                    item = record(number)
                    item.update(id=100 + number, slug=f"course/practice-{number}",
                                title=f"Practice test {number}", isPracticeTest=True,
                                totalPracticeTest=6, totalPracticeTestQuestions=120)
                    records.append(item)
                return {"Course": records, "count": 16}
            return await super().get(path, **params)

    upstream = PracticeSource(remote[0].client, remote[0].base_url)
    with database() as db:
        first = asyncio.run(sync_catalog(db, upstream, get_settings()))
        assert first.count == 30 and first.total == 32
        assert query_courses(db, kind="practice").count == 16
        full = asyncio.run(sync_catalog(db, upstream, get_settings(), full=True))
        assert full.count == full.total == 32
        assert query_courses(db, kind="practice").count == 17
        assert query_courses(db, kind="courses").count == 15
        assert db.get(Course, 116).total_practice_test_questions == 120
        asyncio.run(sync_catalog(db, upstream, get_settings(), full=True))
        assert db.scalar(select(func.count(Course.id))) == 32


def test_catalog_statistics_use_three_queries(populated, database):
    from sqlalchemy import event
    from app.services.catalog import catalog_stats

    queries = []
    with database() as db:
        def capture(connection, cursor, statement, parameters, context, executemany):
            queries.append(statement)
        event.listen(db.bind, "before_cursor_execute", capture)
        try:
            stats = catalog_stats(db, "test-visitor")
        finally:
            event.remove(db.bind, "before_cursor_execute", capture)
    assert stats.total == 16 and stats.active == 15 and stats.practice_tests == 1
    assert stats.saved == 0
    assert len(queries) == 3


def test_upsert_fetches_existing_courses_once_per_batch_off_event_loop(database, remote):
    import threading
    from sqlalchemy import event

    reads, database_threads = [], []
    loop_thread = threading.get_ident()

    def capture(connection, cursor, statement, parameters, context, executemany):
        database_threads.append(threading.get_ident())
        if statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement)

    with database() as db:
        event.listen(db.bind, "before_cursor_execute", capture)
        try:
            for _ in range(2):
                reads.clear()
                count = asyncio.run(upsert_records(db, remote[0], get_settings(), [record(i) for i in range(1, 16)]))
                assert count == 15
                assert len(reads) == 1
        finally:
            event.remove(db.bind, "before_cursor_execute", capture)
        assert db.scalar(select(func.count(Course.id))) == 15
    assert database_threads and loop_thread not in database_threads


def test_upsert_preserves_identity_details_and_cover_when_source_id_changes(database, remote, monkeypatch):
    import app.services.catalog as catalog

    async def missing_cover(*args):
        return None

    with database() as db:
        asyncio.run(upsert_records(db, remote[0], get_settings(), [record(1, detail=True)], detail=True))
        original_cover = db.get(Course, 1).blob_path
        monkeypatch.setattr(catalog, "download_cover", missing_cover)
        changed = {**record(1), "id": 101, "title": "Updated course"}
        asyncio.run(upsert_records(db, remote[0], get_settings(), [changed]))
        course = db.get(Course, 1)
        assert course.title == "Updated course"
        assert course.blob_path == original_cover
        assert course.coupon_code == "TEST-1" and course.total_section == 6
        assert db.get(Course, 101) is None


def test_upsert_handles_repeated_and_renamed_courses_within_one_batch(database, remote):
    with database() as db:
        first = record(1)
        renamed = {**first, "slug": "course/renamed-course", "title": "Renamed course"}
        reused = {**first, "id": 2, "title": "Another course"}
        duplicate = {**renamed, "id": 3, "title": "Last update wins"}
        asyncio.run(upsert_records(db, remote[0], get_settings(), [first, renamed, reused, duplicate]))
        assert db.scalar(select(func.count(Course.id))) == 2
        assert db.get(Course, 1).title == "Last update wins"
        assert db.get(Course, 1).slug == "course/renamed-course"
        assert db.get(Course, 2).slug == first["slug"]
        assert db.get(Course, 3) is None

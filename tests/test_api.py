from fastapi.testclient import TestClient

from app.services.catalog import CATEGORIES

def test_refresh_button_has_no_dialog_or_token(web):
    page = web.get("/courses")
    assert 'data-refresh' in page.text
    assert 'id="refresh-dialog"' not in page.text
    assert 'id="cron-token"' not in page.text
    assert "Token administrator" not in page.text


def test_page_one_refresh_and_legacy_alias_are_idempotent(web):
    response = web.post("/api/catalog/refresh")
    assert response.status_code == 200
    assert response.json()["count"] == 15
    assert response.json()["total"] == 16
    assert "Refreshed page 1 - 15 courses" in response.json()["message"]
    assert response.json()["refreshedAt"]
    assert web.post("/api/catalog/refreshCourses").status_code == 200
    assert web.get("/api/stats").json()["total"] == 15


def test_categories_preserve_canonical_order(web):
    assert web.get("/api/info").json()["docs"] == "/api/docs"
    assert [item["name"] for item in web.get("/api/categories").json()] == [
        "Development", "Business", "Finance & Accounting", "IT & Software", "Office Productivity",
        "Personal Development", "Design", "Marketing", "Lifestyle", "Photography & Video", "Health & Fitness", "Music", "Teaching & Academics",
    ]


def test_list_pagination_and_local_covers(populated):
    response = populated.get("/api/courses")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["count"] == 16 and data["totalPages"] == 2
    assert len(data["courses"]) == 15
    for course in data["courses"]:
        assert course["imageUrl"].startswith("/static/blobs/")
        assert populated.get(course["imageUrl"]).status_code == 200
    assert len(populated.get("/api/courses?page=2").json()["courses"]) == 1


def test_detail_flattens_nested_fields_and_related_excludes_current(populated):
    response = populated.get("/api/courses/python-course-1")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["couponCode"] == "TEST-1" and data["totalSection"] == 6
    assert data["udemyId"] == "1001" and data["learnWho"] == ["Build an API"]
    assert data["forWho"] == ["Python learners"] and data["moreinfo"] == "Useful details"
    assert data["requirements"] == ["A computer"]
    related = populated.get("/api/courses/python-course-1/related").json()
    assert len(related) == 3
    assert all(course["id"] != 1 and course["category"] == "Development" for course in related)


def test_category_imports_full_records_and_search_is_local(populated, remote):
    data = populated.get("/api/courses?category=Development").json()
    assert data["count"] == 8
    assert all(course["couponCode"] for course in data["courses"])
    calls = len(remote[1])
    search = populated.get("/api/courses/search?q=python").json()
    assert search["count"] == 16
    assert len(remote[1]) == calls
    assert not any("search" in request.url.params for request in remote[1])


def test_save_toggle_is_persisted_and_scoped_to_browser(populated):
    assert populated.post("/api/saved/1/toggle").json()["saved"] is True
    assert [course["id"] for course in populated.get("/api/saved").json()] == [1]
    assert populated.get("/saved").status_code == 404
    assert 'href="/saved"' not in populated.get("/courses").text
    visitor_cookie = populated.cookies.get("course_visitor")
    populated.cookies.clear()
    assert populated.get("/api/saved").json() == []
    populated.cookies.set("course_visitor", visitor_cookie)
    assert populated.post("/api/saved/1/toggle").json()["saved"] is False
    assert populated.get("/api/saved").json() == []


def test_html_partial_detail_expired_and_api_docs(populated):
    page = populated.get("/courses")
    assert page.status_code == 200 and "Discover Free Courses" in page.text
    assert 'id="api-reference"' not in page.text and 'id="filters"' in page.text
    partial = populated.get("/courses?q=nomatch", headers={"HX-Request": "true"})
    assert "No courses found" in partial.text and "<html" not in partial.text
    restored = populated.get("/courses", headers={"HX-Request": "true", "HX-History-Restore-Request": "true"})
    assert "<html" in restored.text
    detail = populated.get("/course/python-course-1")
    assert detail.status_code == 200 and "TEST-1" in detail.text and "Copy Coupon" in detail.text
    expired = populated.get("/course/python-course-2")
    assert "Coupon expired" in expired.text and 'id="coupon-code"' not in expired.text
    assert populated.get("/api/docs").status_code == 200
    assert populated.get("/docs").status_code == 404
    assert populated.get("/redoc").status_code == 200
    assert populated.get("/openapi.json").status_code == 200


def test_validation_not_found_and_cross_site_protection(populated):
    for url in ["/api/courses?page=0", "/api/courses?sort=unsafe", "/api/courses?category=Unknown"]:
        assert populated.get(url).status_code == 422
    assert populated.get("/api/courses/missing").status_code == 404
    assert populated.get("/course/missing").status_code == 404
    assert populated.post("/api/saved/999/toggle").status_code == 404
    assert populated.post("/api/saved/1/toggle", headers={"Origin": "https://other.test"}).status_code == 403


def test_landing_links_to_catalog_and_search(populated):
    page = populated.get("/")
    assert page.status_code == 200
    assert 'id="hero-title"' in page.text
    assert 'action="/courses"' in page.text
    assert 'name="q"' in page.text
    assert 'id="filters"' not in page.text
    assert 'API Reference' not in page.text
    assert 'href="/courses?category=Development"' in page.text
    result = populated.get("/courses?q=python&page=1")
    assert result.status_code == 200
    assert 'action="/courses"' in result.text
    assert 'Python course 01' in result.text


def test_search_validates_parameters_and_shows_html_errors(populated):
    invalid = [
        {"q": "x" * 301}, {"q": "bad\x00query"}, {"q": "bad\nquery"},
        {"page": "-1"}, {"page": "word"}, {"kind": "other"},
        {"sort": "other"}, {"hide_expired": "other"}, {"category": "Unknown"},
    ]
    for params in invalid:
        api = populated.get("/api/courses/search", params=params)
        assert api.status_code == 422
        assert "detail" in api.json()
        page = populated.get("/courses", params=params)
        assert page.status_code == 422
        assert "text/html" in page.headers["content-type"]
        assert "Invalid search" in page.text
    response = populated.get("/api/courses/search", params={"q": "  Python  "})
    assert response.status_code == 200 and response.json()["count"] == 16
    assert populated.get("/api/courses/search", params={"q": " " * 300}).json()["count"] == 16
    assert populated.get("/api/courses/search", params={"q": "x" * 300}).status_code == 200


def test_search_treats_wildcards_and_sql_as_literal_text(populated, remote):
    calls = len(remote[1])
    for query in ["%", "_", "' OR 1=1 --", "'; DROP TABLE courses; --"]:
        result = populated.get("/api/courses/search", params={"q": query})
        assert result.status_code == 200
        assert result.json()["count"] == 0
    assert populated.get("/api/courses/search?q=Python").json()["count"] == 16
    assert len(remote[1]) == calls


def test_search_escapes_html_and_clamps_pagination(populated):
    payload = '"><script>alert(1)</script>'
    page = populated.get("/courses", params={"q": payload})
    assert payload not in page.text and "&lt;script&gt;" in page.text
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["x-content-type-options"] == "nosniff"
    result = populated.get("/api/courses/search", params={"page": 100000}).json()
    assert result["page"] == result["totalPages"] == 2
    assert len(result["courses"]) == 1


def test_refresh_cooldown_blocks_repeated_work_and_releases_lock(web, database, remote, monkeypatch):
    from datetime import timedelta
    from app.config import get_settings
    from app.models import utcnow
    from app.services.catalog import meta, set_meta

    monkeypatch.setattr(get_settings(), "refresh_cooldown_seconds", 60)
    assert web.post("/api/catalog/refresh").status_code == 200
    calls = len(remote[1])
    response = web.post("/api/catalog/refresh?full=true")
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert len(remote[1]) == calls
    with database() as db:
        assert meta(db, "sync_state") == "idle"
        assert meta(db, "sync_lock") == ""
        set_meta(db, "refresh_attempted_at", (utcnow() - timedelta(seconds=61)).isoformat())
        db.commit()
    assert web.post("/api/catalog/refresh?full=true").status_code == 200


def test_saved_tab_includes_both_types_and_isolates_visitors(populated, remote):
    for course_id in (1, 3):
        assert populated.post(f"/api/saved/{course_id}/toggle").json()["saved"]
    calls = len(remote[1])
    result = populated.get("/api/courses?kind=saved")
    assert {course["id"] for course in result.json()["courses"]} == {1, 3}
    assert result.headers["cache-control"] == "private, no-store"
    assert "Cookie" in result.headers["vary"]
    page = populated.get("/courses?kind=saved")
    assert 'value="saved" checked' in page.text
    assert 'value="courses" checked' not in page.text
    assert "2</strong> saved courses" in page.text
    assert populated.get("/api/courses/search?kind=saved&q=03").json()["count"] == 1
    assert populated.get("/api/courses?kind=saved&category=Business").json()["count"] == 0
    assert "No saved courses match" in populated.get("/courses?kind=saved&q=nomatch").text
    assert len(remote[1]) == calls
    populated.cookies.clear()
    assert populated.get("/api/courses?kind=saved").json()["count"] == 0
    assert "No saved courses yet" in populated.get("/courses?kind=saved").text


def test_saved_tab_pagination_and_partial_update_after_removal(populated):
    for course_id in range(1, 17):
        assert populated.post(f"/api/saved/{course_id}/toggle").status_code == 200
    page = populated.get("/courses?kind=saved")
    assert 'kind=saved' in page.text
    result = populated.get("/api/courses?kind=saved&page=2").json()
    assert result["count"] == 16 and len(result["courses"]) == 1
    assert populated.post("/api/saved/1/toggle").json()["saved"] is False
    partial = populated.get("/courses?kind=saved", headers={"HX-Request": "true"})
    assert "<html" not in partial.text
    assert 'data-course-id="1"' not in partial.text
    assert '15</strong> saved courses' in partial.text

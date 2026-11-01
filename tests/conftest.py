import asyncio
from io import BytesIO
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["INITIAL_SYNC_ENABLED"] = "false"
os.environ["REFRESH_COOLDOWN_SECONDS"] = "0"

import httpx
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db, make_engine
from app.main import create_app
import app.main as main_module
from app.services.upstream import Upstream


def record(course_id, detail=False):
    result = {
        "id": course_id, "title": f"Python course {course_id:02}",
        "slug": f"course/python-course-{course_id}", "instructor": "Fixture Instructor",
        "imageUrl": f"https://img-c.udemycdn.com/course/{course_id}.jpg",
        "totalHour": 2.5, "rate": 4.0 + (course_id % 10) / 10,
        "category": "Development" if course_id <= 8 else "Business",
        "description": "Learn Python and SQL with practical examples.",
        "language": "English", "badge": "New",
        "createdAt": f"2026-01-{course_id:02}T12:00:00Z",
        "isExpired": course_id == 2, "isPracticeTest": course_id == 3,
        "totalPracticeTest": 2 if course_id == 3 else 0,
        "totalPracticeTestQuestions": 100 if course_id == 3 else 0,
    }
    if detail:
        result.update(enrollUrl=f"https://www.udemy.com/course/fixture-{course_id}/?couponCode=TEST-{course_id}",
                      moreinfo="<p>Useful details</p><script>do_not_render()</script>", totalSection=6, udemyId=1000 + course_id,
                      CourseLearnWho=[{"id": 1, "learnWho": {"id": 2, "description": "Build an API"}}],
                      CourseForWho=[{"forWho": {"text": "Python learners"}}], requirements=[{"description": "A computer"}])
    return result


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main_module, "engine", engine)
    monkeypatch.setattr(main_module, "SessionLocal", factory)
    monkeypatch.setattr(get_settings(), "blob_dir", tmp_path / "blobs")
    yield factory
    engine.dispose()


@pytest.fixture
def remote():
    image = BytesIO()
    Image.new("RGB", (800, 450), "#a62d60").save(image, format="JPEG")
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "img-c.udemycdn.com":
            return httpx.Response(200, content=image.getvalue(), headers={"Content-Type": "image/jpeg"})
        if request.url.path.endswith("/course/detail/category"):
            return httpx.Response(200, json=[record(i, detail=True) for i in range(1, 17) if record(i)["category"] == request.url.params["category"]])
        if request.url.path.endswith("/course/detail"):
            course_id = int(request.url.params["slug"].rsplit("-", 1)[-1])
            return httpx.Response(200, json=record(course_id, detail=True))
        if request.url.path.endswith("/course"):
            if request.url.params.get("type") == "practice-test":
                return httpx.Response(200, json={"Course": [], "count": 0})
            page = int(request.url.params.get("page", 1))
            ids = range(1, 16) if page == 1 else (range(16, 17) if page == 2 else [])
            return httpx.Response(200, json={"Course": [record(i) for i in ids], "count": 16})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    upstream = Upstream(client, "https://upstream.test/api")
    yield upstream, requests
    asyncio.run(client.aclose())


@pytest.fixture
def web(database, remote):
    application = create_app()

    def db_override():
        with database() as db:
            yield db

    application.dependency_overrides[get_db] = db_override
    with TestClient(application) as client:
        application.state.upstream = remote[0]
        yield client


@pytest.fixture
def populated(web):
    response = web.post("/api/catalog/refresh?full=true")
    assert response.status_code == 200, response.text
    return web

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient

from app.config import get_settings
import app.main as main_module


def test_catalog_schedule_every_quarter_hour_from_midnight(database, monkeypatch):
    schedulers = []

    class CapturedScheduler(BackgroundScheduler):
        def start(self):
            schedulers.append(self)

        def shutdown(self, wait=True):
            pass

    monkeypatch.setattr(main_module, "BackgroundScheduler", CapturedScheduler)
    monkeypatch.setattr(get_settings(), "scheduler_enabled", True)
    with TestClient(main_module.create_app()):
        job = schedulers[0].get_job("catalog")
        assert job.func is main_module.scheduled_sync
        assert job.max_instances == 1
        assert job.coalesce is True
        midnight = datetime(2026, 11, 2, tzinfo=ZoneInfo("Asia/Jakarta"))
        previous = None
        now = midnight - timedelta(seconds=1)
        for index in range(97):
            upcoming = job.trigger.get_next_fire_time(previous, now)
            assert upcoming == midnight + timedelta(minutes=15 * index)
            previous = upcoming
            now = upcoming + timedelta(seconds=1)

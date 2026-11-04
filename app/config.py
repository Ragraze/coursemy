from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_name: str = "Coursemy"
    upstream_api_base: HttpUrl
    database_url: str = "sqlite:///./coursemy.db"
    blob_dir: Path = ROOT / "app/static/blobs"
    scheduler_enabled: bool = True
    initial_sync_enabled: bool = True
    cookie_secure: bool = False
    refresh_cooldown_seconds: int = Field(default=60, ge=0, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_and_downgrade(tmp_path, monkeypatch):
    from app.config import get_settings

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setattr(get_settings(), "database_url", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    assert {"courses", "saved_courses", "catalog_meta"}.issubset(inspector.get_table_names())
    assert "detail_fetched_at" in {column["name"] for column in inspector.get_columns("courses")}
    assert inspector.get_unique_constraints("saved_courses")[0]["column_names"] == ["visitor_id", "course_id"]
    command.downgrade(config, "base")
    assert "courses" not in inspect(engine).get_table_names()
    engine.dispose()

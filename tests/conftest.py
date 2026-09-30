import pytest
from sqlalchemy import text


def _db_ready() -> bool:
    try:
        from app.database import owner_engine

        with owner_engine().connect() as conn:
            return conn.execute(text("SELECT count(*) FROM olist.orders")).scalar_one() > 0
    except Exception:  # noqa: BLE001
        return False


DB_READY = _db_ready()


def pytest_collection_modifyitems(items):
    skip = pytest.mark.skip(reason="PostgreSQL with loaded Olist data not available")
    for item in items:
        if "integration" in item.keywords and not DB_READY:
            item.add_marker(skip)

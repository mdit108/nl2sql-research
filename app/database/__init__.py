from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.config import get_settings


@lru_cache
def owner_engine() -> Engine:
    """Owner connection: migrations, loading, knowledge store. Never runs model SQL."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def readonly_engine() -> Engine:
    """Read-only connection: the only engine that executes generated SQL."""
    return create_engine(get_settings().readonly_database_url, pool_pre_ping=True)

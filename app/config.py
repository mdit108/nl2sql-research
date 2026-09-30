"""All runtime configuration comes from environment variables (or .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://nl2sql_owner@localhost:5432/nl2sql_research"
    readonly_database_url: str = "postgresql+psycopg://nl2sql_readonly@localhost:5432/nl2sql_research"
    statement_timeout_ms: int = 15000
    max_result_rows: int = 5000

    llm_provider: str = "mock"
    llm_base_url: str | None = None
    # SecretStr keeps the key out of repr() and logs.
    llm_api_key: SecretStr | None = None
    llm_model: str = "mock"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096

    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None

    retrieval_top_k: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()

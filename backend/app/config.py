"""Application settings loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://cgq_app:cgq_local_dev@localhost:5433/cgq"
    # Used only by the backend test suite; tests drop and recreate this database's tables.
    test_database_url: str | None = None
    # Comma-separated list of browser origins allowed to call the API directly.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_file: Path = REPO_ROOT / "data" / "seed" / "questions.json"
    audit_file: Path = REPO_ROOT / "data" / "seed" / "answer_key_audit.csv"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

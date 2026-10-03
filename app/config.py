"""Application settings loaded from environment variables and the `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Финансовый ассистент"
    debug: bool = False
    database_url: str = "sqlite:///data/finance.db"
    # Timeout of one request to an online exchange rate source.
    rate_request_timeout_seconds: float = 5.0
    # How far (in days) a rate from the system's own history may be from the operation date.
    rate_history_max_days: int = Field(default=7, ge=0)

    @field_validator("database_url")
    @classmethod
    def resolve_sqlite_path(cls, value: str) -> str:
        """Make relative SQLite paths independent of the current working directory."""
        url = make_url(value)
        if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
            return value
        db_path = Path(url.database)
        if not db_path.is_absolute():
            db_path = BASE_DIR / db_path
        return url.set(database=db_path.as_posix()).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()

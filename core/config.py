"""Runtime configuration resolved from Streamlit secrets and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "app.db"


@dataclass(frozen=True)
class Settings:
    """Resolved application settings."""

    gemini_api_key: str
    database_url: str
    sqlite_url: str
    postgres_url: str
    model_page_size: int
    sqlite_path: Path

    def resolve_url(self, backend: str | None = None) -> str:
        """Return the active database URL based on the requested backend."""
        if backend == "SQLite":
            return self.sqlite_url
        if backend == "PostgreSQL":
            return self.postgres_url or self.database_url
        return self.database_url


def _secret(name: str) -> str | None:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        return None
    return None


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    secret = _secret(name)
    if secret:
        return secret
    return default


def get_settings() -> Settings:
    """Build a Settings object from the current environment."""
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sqlite_url = f"sqlite+pysqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"

    raw_db_url = _get("DATABASE_URL").strip()
    postgres_url = raw_db_url if "postgres" in raw_db_url.lower() else ""

    primary_url = raw_db_url if raw_db_url else sqlite_url

    raw_page_size = _get("GEMINI_MODEL_PAGE_SIZE", "200").strip()
    try:
        page_size = max(1, int(raw_page_size))
    except ValueError:
        page_size = 200

    return Settings(
        gemini_api_key=_get("GEMINI_API_KEY").strip(),
        database_url=primary_url,
        sqlite_url=sqlite_url,
        postgres_url=postgres_url,
        model_page_size=page_size,
        sqlite_path=DEFAULT_SQLITE_PATH,
    )

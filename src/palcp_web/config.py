"""Application configuration, read from the environment.

Railway injects ``DATABASE_URL`` (from the Postgres plugin) and ``PORT``. We read
everything from ``os.environ`` to avoid extra dependencies.
"""

from __future__ import annotations

import os
import secrets


def _normalize_db_url(url: str) -> str:
    """Make a Railway/Heroku-style Postgres URL work with SQLAlchemy + psycopg3.

    * ``postgres://``         -> ``postgresql+psycopg://``
    * ``postgresql://``       -> ``postgresql+psycopg://``
    * already-qualified URLs and SQLite URLs are returned unchanged.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings:
    """Runtime settings. Instantiated once as :data:`settings`."""

    def __init__(self) -> None:
        # Database: default to a local SQLite file for development/tests.
        raw_db = os.environ.get("DATABASE_URL", "sqlite:///./palcp_web.db")
        self.database_url = _normalize_db_url(raw_db)
        self.is_sqlite = self.database_url.startswith("sqlite")

        # Session signing key. MUST be set in production; a random per-process
        # key is used otherwise (which logs everyone out on restart).
        self.secret_key = os.environ.get("SECRET_KEY", "")
        self.secret_key_was_generated = not self.secret_key
        if not self.secret_key:
            self.secret_key = secrets.token_urlsafe(48)

        self.port = int(os.environ.get("PORT", "8000"))
        self.session_cookie = os.environ.get("SESSION_COOKIE", "palcp_session")
        # Cookies over HTTPS only in production (Railway serves HTTPS).
        self.session_https_only = os.environ.get("SESSION_HTTPS_ONLY", "1") != "0"
        self.app_name = "PA-LCP-Tool"


settings = Settings()

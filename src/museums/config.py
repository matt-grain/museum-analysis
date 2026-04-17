"""Centralized settings via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, HttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from museums.enums.log_level import LogLevel


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MUSEUMS_")

    database_url: PostgresDsn = PostgresDsn("postgresql+asyncpg://museums:museums@db:5432/museums")
    database_echo: bool = False

    refresh_cooldown_hours: int = Field(default=24, ge=1, le=168)

    http_connect_timeout_seconds: float = 5.0
    http_read_timeout_seconds: float = 30.0
    http_max_retries: int = Field(default=3, ge=1, le=10)

    mediawiki_base_url: HttpUrl = HttpUrl("https://en.wikipedia.org/w/api.php")
    wikidata_sparql_url: HttpUrl = HttpUrl("https://query.wikidata.org/sparql")
    wikipedia_list_page_title: str = "List_of_most_visited_museums"

    museum_visitor_threshold: int = 2_000_000

    log_level: LogLevel = LogLevel.INFO
    user_agent: str = "MuseumsApp/0.1 (https://github.com/example/museums)"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()

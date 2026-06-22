"""Environment-based application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
VALID_SAFE_SEARCH_VALUES = {"none", "moderate", "strict"}


def _read_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} debe ser true o false (también se aceptan 1/0, yes/no y on/off)."
    )


def _read_port() -> int:
    raw_value = os.getenv("APP_PORT", "8000").strip()
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError("APP_PORT debe ser un número entero.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("APP_PORT debe estar entre 1 y 65535.")
    return port


@dataclass(frozen=True, slots=True)
class Settings:
    youtube_api_key: str | None
    youtube_region_code: str
    youtube_relevance_language: str
    youtube_safe_search: str
    youtube_music_only: bool
    app_port: int
    database_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        safe_search = os.getenv("YOUTUBE_SAFE_SEARCH", "none").strip().lower()
        if safe_search not in VALID_SAFE_SEARCH_VALUES:
            choices = ", ".join(sorted(VALID_SAFE_SEARCH_VALUES))
            raise ValueError(f"YOUTUBE_SAFE_SEARCH debe ser uno de: {choices}.")

        api_key = os.getenv("YOUTUBE_API_KEY", "").strip() or None
        region_code = os.getenv("YOUTUBE_REGION_CODE", "ES").strip().upper() or "ES"
        relevance_language = (
            os.getenv("YOUTUBE_RELEVANCE_LANGUAGE", "es").strip() or "es"
        )

        return cls(
            youtube_api_key=api_key,
            youtube_region_code=region_code,
            youtube_relevance_language=relevance_language,
            youtube_safe_search=safe_search,
            youtube_music_only=_read_bool("YOUTUBE_MUSIC_ONLY", False),
            app_port=_read_port(),
            database_url=os.getenv("DATABASE_URL", "").strip() or None,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()

"""Shared profile constants and validation."""

from __future__ import annotations

import re


DEFAULT_PROFILE_ID = "familia"
PROFILE_ID_MAX_LENGTH = 64
_PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def validate_profile_id(profile_id: str | None) -> str:
    cleaned = (profile_id or DEFAULT_PROFILE_ID).strip().lower()
    if not _PROFILE_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "profile_id debe usar letras minúsculas, números, guiones o guiones bajos."
        )
    return cleaned

"""Resolve YouTube videos to browser-friendly audio streams with yt-dlp."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

import yt_dlp
from yt_dlp.utils import DownloadError


YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class AudioExtractionError(Exception):
    """Raised when an audio source cannot be resolved."""


@dataclass(frozen=True)
class AudioSource:
    url: str
    content_type: str
    http_headers: dict[str, str]


class AudioResolver:
    """Resolve and briefly cache expiring media URLs returned by yt-dlp."""

    def __init__(self, cache_ttl_seconds: int = 600) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, AudioSource]] = {}
        self._lock = asyncio.Lock()

    async def resolve(self, video_id: str) -> AudioSource:
        if not YOUTUBE_VIDEO_ID.fullmatch(video_id):
            raise AudioExtractionError("El identificador de la canción no es válido.")

        now = time.monotonic()
        cached = self._cache.get(video_id)
        if cached and cached[0] > now:
            return cached[1]

        async with self._lock:
            cached = self._cache.get(video_id)
            if cached and cached[0] > time.monotonic():
                return cached[1]

            source = await asyncio.to_thread(_extract_audio_source, video_id)
            self._cache[video_id] = (
                time.monotonic() + self._cache_ttl_seconds,
                source,
            )
            return source


def _extract_audio_source(video_id: str) -> AudioSource:
    options = {
        "format": "m4a/bestaudio[ext=m4a]/bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 15,
        "cachedir": False,
    }

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
    except DownloadError as exc:
        raise AudioExtractionError(
            "No se ha podido preparar el audio de esta canción. Prueba con otra."
        ) from exc
    except Exception as exc:
        raise AudioExtractionError(
            "Ha ocurrido un problema al preparar el audio. Inténtalo de nuevo."
        ) from exc

    media_url = info.get("url") if isinstance(info, dict) else None
    if not isinstance(media_url, str) or not media_url.startswith("https://"):
        raise AudioExtractionError(
            "YouTube no ha proporcionado audio reproducible para esta canción."
        )

    extension = str(info.get("ext", "")).lower()
    content_type = {
        "m4a": "audio/mp4",
        "mp4": "audio/mp4",
        "webm": "audio/webm",
        "opus": "audio/ogg",
        "ogg": "audio/ogg",
    }.get(extension, "audio/mpeg")
    raw_headers = info.get("http_headers") or {}
    http_headers = {
        str(key): str(value)
        for key, value in raw_headers.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    return AudioSource(media_url, content_type, http_headers)

"""Resolve YouTube videos to browser-friendly audio streams with yt-dlp."""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
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

    def __init__(
        self,
        cache_ttl_seconds: int = 600,
        max_cache_entries: int = 128,
        max_concurrent_extractions: int = 4,
    ) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds
        self._max_cache_entries = max_cache_entries
        self._cache: OrderedDict[str, tuple[float, AudioSource]] = OrderedDict()
        self._extraction_slots = asyncio.Semaphore(max_concurrent_extractions)

    async def resolve(self, video_id: str) -> AudioSource:
        if not YOUTUBE_VIDEO_ID.fullmatch(video_id):
            raise AudioExtractionError("El identificador de la canción no es válido.")

        if cached := self._get_cached(video_id):
            return cached

        async with self._extraction_slots:
            if cached := self._get_cached(video_id):
                return cached

            source = await asyncio.to_thread(_extract_audio_source, video_id)
            self._store(video_id, source)
            return source

    async def filter_playable(
        self,
        results: list[dict[str, str]],
        *,
        limit: int = 10,
        batch_size: int = 10,
    ) -> list[dict[str, str]]:
        """Keep search order while discarding videos yt-dlp cannot resolve."""

        playable: list[dict[str, str]] = []

        async def check(result: dict[str, str]) -> dict[str, str] | None:
            try:
                await self.resolve(result["video_id"])
            except AudioExtractionError:
                return None
            return result

        for offset in range(0, len(results), batch_size):
            batch = results[offset : offset + batch_size]
            checked = await asyncio.gather(*(check(result) for result in batch))
            playable.extend(result for result in checked if result is not None)
            if len(playable) >= limit:
                break

        return playable[:limit]

    def _get_cached(self, video_id: str) -> AudioSource | None:
        cached = self._cache.get(video_id)
        if cached is None:
            return None
        if cached[0] <= time.monotonic():
            self._cache.pop(video_id, None)
            return None
        self._cache.move_to_end(video_id)
        return cached[1]

    def _store(self, video_id: str, source: AudioSource) -> None:
        now = time.monotonic()
        for cached_id, (expires_at, _) in list(self._cache.items()):
            if expires_at <= now:
                self._cache.pop(cached_id, None)

        self._cache[video_id] = (now + self._cache_ttl_seconds, source)
        self._cache.move_to_end(video_id)
        while len(self._cache) > self._max_cache_entries:
            self._cache.popitem(last=False)


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

"""Small async client for the YouTube Data API v3."""

from __future__ import annotations

from html import unescape
from typing import Any

import httpx

from app.settings import Settings


YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YouTubeSearchError(Exception):
    """An error safe to expose to the web client."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        reason = payload.get("error", {}).get("message")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    except (ValueError, AttributeError):
        pass
    return "YouTube no ha podido completar la búsqueda."


def _normalise_results(payload: dict[str, Any]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        thumbnail = (
            thumbnails.get("high")
            or thumbnails.get("medium")
            or thumbnails.get("default")
            or {}
        )

        if not video_id:
            continue

        results.append(
            {
                "video_id": str(video_id),
                "title": unescape(str(snippet.get("title", "Vídeo sin título"))),
                "channel_title": unescape(
                    str(snippet.get("channelTitle", "Canal desconocido"))
                ),
                "thumbnail_url": str(thumbnail.get("url", "")),
            }
        )
    return results[:10]


async def search_videos(query: str, settings: Settings) -> list[dict[str, str]]:
    """Search YouTube and return only the fields consumed by the UI."""

    params: dict[str, str | int] = {
        "part": "snippet",
        "q": query,
        "key": settings.youtube_api_key or "",
        "type": "video",
        "maxResults": 10,
        "order": "relevance",
        "regionCode": settings.youtube_region_code,
        "relevanceLanguage": settings.youtube_relevance_language,
        "safeSearch": settings.youtube_safe_search,
    }
    if settings.youtube_music_only:
        params["videoCategoryId"] = "10"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(YOUTUBE_SEARCH_URL, params=params)
    except httpx.TimeoutException as exc:
        raise YouTubeSearchError(
            "YouTube está tardando demasiado. Inténtalo de nuevo.", status_code=504
        ) from exc
    except httpx.RequestError as exc:
        raise YouTubeSearchError(
            "No se ha podido conectar con YouTube. Comprueba la conexión a Internet."
        ) from exc

    if response.is_error:
        reason = _error_message(response)
        if response.status_code in {400, 401, 403}:
            raise YouTubeSearchError(
                f"YouTube ha rechazado la búsqueda: {reason}", status_code=502
            )
        raise YouTubeSearchError(
            "YouTube no está disponible ahora mismo. Inténtalo de nuevo.",
            status_code=502,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise YouTubeSearchError("YouTube ha devuelto una respuesta no válida.") from exc

    return _normalise_results(payload)

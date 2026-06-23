"""FastAPI entry point for Kids YouTube Jukebox."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.audio import AudioExtractionError, AudioResolver
from app.database import open_database
from app.history import HistoryRepository, NoOpHistoryRepository
from app.profiles import DEFAULT_PROFILE_ID, PROFILE_ID_MAX_LENGTH, validate_profile_id
from app.settings import Settings, get_settings
from app.youtube import YouTubeSearchError, search_videos


STATIC_DIR = Path(__file__).parent / "static"
SEARCH_RESULT_LIMIT = 20
audio_resolver = AudioResolver()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    database = await open_database(get_settings())
    application.state.database = database
    application.state.history_repository = database.repository
    try:
        yield
    finally:
        await database.close()


app = FastAPI(
    title="Kids YouTube Jukebox",
    description="Buscador de YouTube con reproducción de audio mediante yt-dlp.",
    version="2.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PlaybackCreate(BaseModel):
    search_id: int = Field(gt=0)
    video_id: str = Field(min_length=1, max_length=32)


class FavoriteCreate(BaseModel):
    video_id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=500)
    channel_title: str = Field(min_length=1, max_length=500)
    thumbnail_url: str = Field(min_length=1, max_length=2000)
    search_id: int | None = Field(default=None, gt=0)
    profile_id: str = Field(
        default=DEFAULT_PROFILE_ID,
        min_length=1,
        max_length=PROFILE_ID_MAX_LENGTH,
    )


def get_history_repository(request: Request) -> HistoryRepository:
    return getattr(
        request.app.state,
        "history_repository",
        NoOpHistoryRepository(),
    )


def get_audio_resolver() -> AudioResolver:
    return audio_resolver


def read_profile_id(
    profile_id: Annotated[
        str,
        Query(min_length=1, max_length=PROFILE_ID_MAX_LENGTH),
    ] = DEFAULT_PROFILE_ID,
) -> str:
    try:
        return validate_profile_id(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/search")
async def search(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    settings: Annotated[Settings, Depends(get_settings)],
    history: Annotated[HistoryRepository, Depends(get_history_repository)],
    resolver: Annotated[AudioResolver, Depends(get_audio_resolver)],
) -> dict[str, object]:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Escribe una canción para buscar.")
    if not settings.youtube_api_key:
        await history.record_search(
            query,
            settings,
            [],
            status="configuration_error",
            error_message="Falta YOUTUBE_API_KEY.",
        )
        raise HTTPException(
            status_code=503,
            detail="Falta YOUTUBE_API_KEY en la configuración del servidor.",
        )

    try:
        candidates = await search_videos(query, settings)
        results = await resolver.filter_playable(candidates, limit=SEARCH_RESULT_LIMIT)
    except YouTubeSearchError as exc:
        await history.record_search(
            query,
            settings,
            [],
            status="youtube_error",
            error_message=exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    search_id = await history.record_search(
        query,
        settings,
        results,
        status="success" if results else "no_results",
    )
    return {"query": query, "search_id": search_id, "results": results}


@app.post("/api/playback", status_code=201)
async def record_playback(
    playback: PlaybackCreate,
    history: Annotated[HistoryRepository, Depends(get_history_repository)],
) -> dict[str, object]:
    if not history.enabled:
        return {"recorded": False, "playback": None}

    recorded = await history.record_playback(playback.search_id, playback.video_id)
    if recorded is None:
        raise HTTPException(
            status_code=404,
            detail="El vídeo no pertenece a la búsqueda indicada.",
        )
    return {"recorded": True, "playback": recorded}


@app.get("/api/favorites")
async def favorites(
    repository: Annotated[HistoryRepository, Depends(get_history_repository)],
    profile_id: Annotated[str, Depends(read_profile_id)],
) -> dict[str, object]:
    return await repository.list_favorites(profile_id)


@app.post("/api/favorites", status_code=201)
async def add_favorite(
    favorite: FavoriteCreate,
    repository: Annotated[HistoryRepository, Depends(get_history_repository)],
) -> dict[str, object]:
    if not repository.enabled:
        raise HTTPException(
            status_code=503,
            detail="Las favoritas requieren PostgreSQL en este servidor.",
        )

    try:
        profile_id = validate_profile_id(favorite.profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    saved = await repository.add_favorite(
        {
            "video_id": favorite.video_id,
            "title": favorite.title,
            "channel_title": favorite.channel_title,
            "thumbnail_url": favorite.thumbnail_url,
        },
        favorite.search_id,
        profile_id,
    )
    return {"enabled": True, "profile_id": profile_id, "favorite": saved}


@app.delete("/api/favorites/{video_id}")
async def remove_favorite(
    video_id: str,
    repository: Annotated[HistoryRepository, Depends(get_history_repository)],
    profile_id: Annotated[str, Depends(read_profile_id)],
) -> dict[str, object]:
    if not repository.enabled:
        raise HTTPException(
            status_code=503,
            detail="Las favoritas requieren PostgreSQL en este servidor.",
        )

    return {
        "enabled": True,
        "profile_id": profile_id,
        "removed": await repository.remove_favorite(video_id, profile_id),
    }


@app.get("/api/audio/{video_id}")
async def stream_audio(
    video_id: str,
    request: Request,
    resolver: Annotated[AudioResolver, Depends(get_audio_resolver)],
) -> StreamingResponse:
    try:
        source = await resolver.resolve(video_id)
    except AudioExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    upstream_headers = dict(source.http_headers)
    upstream_headers["Accept-Encoding"] = "identity"
    if byte_range := request.headers.get("range"):
        upstream_headers["Range"] = byte_range

    client = httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(connect=15, read=None, write=15, pool=15),
    )
    try:
        upstream = await client.send(
            client.build_request("GET", source.url, headers=upstream_headers),
            stream=True,
        )
    except httpx.RequestError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="No se ha podido conectar con el servidor de audio.",
        ) from exc

    if upstream.status_code not in {200, 206}:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="YouTube no ha permitido reproducir el audio de esta canción.",
        )

    response_headers = {
        name: value
        for name in ("content-length", "content-range", "accept-ranges")
        if (value := upstream.headers.get(name)) is not None
    }

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", source.content_type),
        headers=response_headers,
    )


@app.get("/api/history")
async def history(
    repository: Annotated[HistoryRepository, Depends(get_history_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    return await repository.recent_history(limit)


@app.get("/health")
async def health(
    repository: Annotated[HistoryRepository, Depends(get_history_repository)],
) -> dict[str, object]:
    connected = await repository.ping() if repository.enabled else False
    return {
        "status": "ok",
        "database": {"enabled": repository.enabled, "connected": connected},
    }

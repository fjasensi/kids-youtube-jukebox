"""FastAPI entry point for Kids YouTube Jukebox."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.database import open_database
from app.history import HistoryRepository, NoOpHistoryRepository
from app.settings import Settings, get_settings
from app.youtube import YouTubeSearchError, search_videos


STATIC_DIR = Path(__file__).parent / "static"


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
    description="Buscador y reproductor casero basado en las API oficiales de YouTube.",
    version="1.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PlaybackCreate(BaseModel):
    search_id: int = Field(gt=0)
    video_id: str = Field(min_length=1, max_length=32)


def get_history_repository(request: Request) -> HistoryRepository:
    return getattr(
        request.app.state,
        "history_repository",
        NoOpHistoryRepository(),
    )


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/search")
async def search(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    settings: Annotated[Settings, Depends(get_settings)],
    history: Annotated[HistoryRepository, Depends(get_history_repository)],
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
        results = await search_videos(query, settings)
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

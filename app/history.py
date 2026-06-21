"""Persistence service for searches and playback history."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models import PlaybackEvent, SearchEvent, SearchResultRecord
from app.settings import Settings


class HistoryRepository(Protocol):
    enabled: bool

    async def record_search(
        self,
        query: str,
        settings: Settings,
        results: list[dict[str, str]],
        *,
        status: str,
        error_message: str | None = None,
    ) -> int | None: ...

    async def record_playback(self, search_id: int, video_id: str) -> dict[str, Any] | None: ...

    async def recent_history(self, limit: int) -> dict[str, Any]: ...

    async def ping(self) -> bool: ...


class NoOpHistoryRepository:
    enabled = False

    async def record_search(
        self,
        query: str,
        settings: Settings,
        results: list[dict[str, str]],
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        return None

    async def record_playback(self, search_id: int, video_id: str) -> None:
        return None

    async def recent_history(self, limit: int) -> dict[str, Any]:
        return {"enabled": False, "searches": [], "playbacks": []}

    async def ping(self) -> bool:
        return False


class PostgresHistoryRepository:
    enabled = True

    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    async def record_search(
        self,
        query: str,
        settings: Settings,
        results: list[dict[str, str]],
        *,
        status: str,
        error_message: str | None = None,
    ) -> int:
        async with self._session_factory() as session, session.begin():
            search = SearchEvent(
                query=query,
                result_count=len(results),
                status=status,
                error_message=error_message,
                region_code=settings.youtube_region_code,
                relevance_language=settings.youtube_relevance_language,
                safe_search=settings.youtube_safe_search,
                music_only=settings.youtube_music_only,
            )
            session.add(search)
            await session.flush()

            session.add_all(
                SearchResultRecord(
                    search_id=search.id,
                    position=position,
                    video_id=result["video_id"],
                    title=result["title"],
                    channel_title=result["channel_title"],
                    thumbnail_url=result["thumbnail_url"],
                )
                for position, result in enumerate(results, start=1)
            )
            return search.id

    async def record_playback(self, search_id: int, video_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session, session.begin():
            result = await session.scalar(
                select(SearchResultRecord).where(
                    SearchResultRecord.search_id == search_id,
                    SearchResultRecord.video_id == video_id,
                )
            )
            if result is None:
                return None

            playback = PlaybackEvent(
                search_id=search_id,
                video_id=result.video_id,
                title=result.title,
                channel_title=result.channel_title,
                thumbnail_url=result.thumbnail_url,
            )
            session.add(playback)
            await session.flush()
            await session.refresh(playback)
            return _playback_to_dict(playback)

    async def recent_history(self, limit: int) -> dict[str, Any]:
        async with self._session_factory() as session:
            searches = list(
                (
                    await session.scalars(
                        select(SearchEvent)
                        .order_by(SearchEvent.searched_at.desc(), SearchEvent.id.desc())
                        .limit(limit)
                    )
                ).all()
            )
            playbacks = list(
                (
                    await session.scalars(
                        select(PlaybackEvent)
                        .order_by(PlaybackEvent.played_at.desc(), PlaybackEvent.id.desc())
                        .limit(limit)
                    )
                ).all()
            )
        return {
            "enabled": True,
            "searches": [_search_to_dict(item) for item in searches],
            "playbacks": [_playback_to_dict(item) for item in playbacks],
        }

    async def ping(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


def _search_to_dict(search: SearchEvent) -> dict[str, Any]:
    return {
        "id": search.id,
        "query": search.query,
        "result_count": search.result_count,
        "status": search.status,
        "error_message": search.error_message,
        "region_code": search.region_code,
        "relevance_language": search.relevance_language,
        "safe_search": search.safe_search,
        "music_only": search.music_only,
        "searched_at": search.searched_at.isoformat(),
    }


def _playback_to_dict(playback: PlaybackEvent) -> dict[str, Any]:
    return {
        "id": playback.id,
        "search_id": playback.search_id,
        "video_id": playback.video_id,
        "title": playback.title,
        "channel_title": playback.channel_title,
        "thumbnail_url": playback.thumbnail_url,
        "played_at": playback.played_at.isoformat(),
    }

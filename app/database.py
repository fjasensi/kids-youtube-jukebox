"""Database lifecycle helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.history import NoOpHistoryRepository, PostgresHistoryRepository
from app.models import Base
from app.settings import Settings


@dataclass(slots=True)
class DatabaseContext:
    engine: AsyncEngine | None
    repository: NoOpHistoryRepository | PostgresHistoryRepository

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


async def open_database(settings: Settings) -> DatabaseContext:
    if not settings.database_url:
        return DatabaseContext(engine=None, repository=NoOpHistoryRepository())

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except Exception:
        await engine.dispose()
        raise

    return DatabaseContext(
        engine=engine,
        repository=PostgresHistoryRepository(engine),
    )

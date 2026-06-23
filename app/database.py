"""Database lifecycle helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.ext.asyncio import AsyncConnection

from app.history import NoOpHistoryRepository, PostgresHistoryRepository
from app.models import Base
from app.profiles import DEFAULT_PROFILE_ID
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
            await migrate_favorite_profiles(connection)
    except Exception:
        await engine.dispose()
        raise

    return DatabaseContext(
        engine=engine,
        repository=PostgresHistoryRepository(engine),
    )


async def migrate_favorite_profiles(connection: AsyncConnection) -> None:
    """Add lightweight favorite profiles to existing PostgreSQL installs."""

    await connection.execute(
        text("ALTER TABLE favorite_tracks ADD COLUMN IF NOT EXISTS profile_id VARCHAR(64)")
    )
    await connection.execute(
        text("UPDATE favorite_tracks SET profile_id = :profile_id WHERE profile_id IS NULL"),
        {"profile_id": DEFAULT_PROFILE_ID},
    )
    await connection.execute(
        text(
            "ALTER TABLE favorite_tracks "
            f"ALTER COLUMN profile_id SET DEFAULT '{DEFAULT_PROFILE_ID}'"
        )
    )
    await connection.execute(
        text("ALTER TABLE favorite_tracks ALTER COLUMN profile_id SET NOT NULL")
    )
    await connection.execute(
        text(
            """
            DO $$
            DECLARE
                existing_constraint text;
            BEGIN
                SELECT con.conname INTO existing_constraint
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = 'favorite_tracks'
                  AND con.contype = 'u'
                  AND (
                    SELECT array_agg(att.attname::text ORDER BY cols.ordinality)
                    FROM unnest(con.conkey) WITH ORDINALITY AS cols(attnum, ordinality)
                    JOIN pg_attribute att
                      ON att.attrelid = rel.oid
                     AND att.attnum = cols.attnum
                  ) = ARRAY['video_id']::text[];

                IF existing_constraint IS NOT NULL THEN
                    EXECUTE format(
                        'ALTER TABLE favorite_tracks DROP CONSTRAINT %I',
                        existing_constraint
                    );
                END IF;
            END $$;
            """
        )
    )
    await connection.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    WHERE rel.relname = 'favorite_tracks'
                      AND con.conname = 'uq_favorite_tracks_profile_video'
                ) THEN
                    ALTER TABLE favorite_tracks
                    ADD CONSTRAINT uq_favorite_tracks_profile_video
                    UNIQUE (profile_id, video_id);
                END IF;
            END $$;
            """
        )
    )
    await connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_favorite_tracks_profile_favorited_at "
            "ON favorite_tracks (profile_id, favorited_at)"
        )
    )

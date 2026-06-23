"""Database tables for searches, returned videos, playback events, and favorites."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.profiles import DEFAULT_PROFILE_ID


class Base(DeclarativeBase):
    pass


class SearchEvent(Base):
    __tablename__ = "search_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(200), nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    region_code: Mapped[str] = mapped_column(String(8), nullable=False)
    relevance_language: Mapped[str] = mapped_column(String(16), nullable=False)
    safe_search: Mapped[str] = mapped_column(String(16), nullable=False)
    music_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_search_events_searched_at", "searched_at"),)


class SearchResultRecord(Base):
    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("search_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    channel_title: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("search_id", "position", name="uq_search_result_position"),
    )


class PlaybackEvent(Base):
    __tablename__ = "playback_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    search_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("search_events.id", ondelete="SET NULL"),
        index=True,
    )
    video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    channel_title: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(Text, nullable=False)
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_playback_events_played_at", "played_at"),)


class FavoriteTrack(Base):
    __tablename__ = "favorite_tracks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    search_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("search_events.id", ondelete="SET NULL"),
        index=True,
    )
    profile_id: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=DEFAULT_PROFILE_ID
    )
    video_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    channel_title: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(Text, nullable=False)
    favorited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "video_id",
            name="uq_favorite_tracks_profile_video",
        ),
        Index("ix_favorite_tracks_favorited_at", "favorited_at"),
        Index("ix_favorite_tracks_profile_favorited_at", "profile_id", "favorited_at"),
    )

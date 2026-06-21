from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_history_repository
from app.settings import Settings, get_settings
from app.youtube import search_videos


def make_settings(*, api_key: str | None = "test-key", music_only: bool = True) -> Settings:
    return Settings(
        youtube_api_key=api_key,
        youtube_region_code="ES",
        youtube_relevance_language="es",
        youtube_safe_search="none",
        youtube_music_only=music_only,
        app_port=8000,
        database_url=None,
    )


class SettingsTests(unittest.TestCase):
    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()

        self.assertIsNone(settings.youtube_api_key)
        self.assertEqual(settings.youtube_region_code, "ES")
        self.assertEqual(settings.youtube_relevance_language, "es")
        self.assertEqual(settings.youtube_safe_search, "none")
        self.assertTrue(settings.youtube_music_only)
        self.assertEqual(settings.app_port, 8000)
        self.assertIsNone(settings.database_url)

    def test_rejects_invalid_safe_search(self) -> None:
        with patch.dict(os.environ, {"YOUTUBE_SAFE_SEARCH": "invalid"}, clear=True):
            with self.assertRaisesRegex(ValueError, "YOUTUBE_SAFE_SEARCH"):
                Settings.from_env()


class FakeAsyncClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.params: dict[str, str | int] | None = None

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, *, params: dict[str, str | int]) -> httpx.Response:
        self.params = params
        return self.response


class YouTubeClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_required_parameters_and_reduces_response(self) -> None:
        request = httpx.Request("GET", "https://example.test")
        response = httpx.Response(
            200,
            request=request,
            json={
                "nextPageToken": "not-returned",
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "Libre &amp; feliz",
                            "channelTitle": "Canal infantil",
                            "description": "not returned",
                            "thumbnails": {
                                "high": {"url": "https://img.example/abc.jpg"}
                            },
                        },
                    }
                ],
            },
        )
        fake_client = FakeAsyncClient(response)

        with patch("app.youtube.httpx.AsyncClient", return_value=fake_client):
            results = await search_videos("Frozen libre soy", make_settings())

        self.assertEqual(
            fake_client.params,
            {
                "part": "snippet",
                "q": "Frozen libre soy",
                "key": "test-key",
                "type": "video",
                "maxResults": 10,
                "order": "relevance",
                "regionCode": "ES",
                "relevanceLanguage": "es",
                "safeSearch": "none",
                "videoCategoryId": "10",
            },
        )
        self.assertEqual(
            results,
            [
                {
                    "video_id": "abc123",
                    "title": "Libre & feliz",
                    "channel_title": "Canal infantil",
                    "thumbnail_url": "https://img.example/abc.jpg",
                }
            ],
        )

    async def test_music_category_is_optional(self) -> None:
        request = httpx.Request("GET", "https://example.test")
        fake_client = FakeAsyncClient(httpx.Response(200, request=request, json={"items": []}))

        with patch("app.youtube.httpx.AsyncClient", return_value=fake_client):
            await search_videos("dinosaurios", make_settings(music_only=False))

        self.assertNotIn("videoCategoryId", fake_client.params or {})


class ApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_home_serves_the_mobile_app(self) -> None:
        with TestClient(app) as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Disco Estrella", response.text)

    def test_search_reports_missing_api_key(self) -> None:
        app.dependency_overrides[get_settings] = lambda: make_settings(api_key=None)
        repository = FakeHistoryRepository()
        app.dependency_overrides[get_history_repository] = lambda: repository

        with TestClient(app) as client:
            response = client.get("/api/search", params={"q": "Frozen"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("YOUTUBE_API_KEY", response.json()["detail"])
        self.assertEqual(repository.searches[0]["status"], "configuration_error")

    def test_search_returns_expected_shape(self) -> None:
        app.dependency_overrides[get_settings] = make_settings
        repository = FakeHistoryRepository()
        app.dependency_overrides[get_history_repository] = lambda: repository
        expected = [
            {
                "video_id": "abc123",
                "title": "Libre soy",
                "channel_title": "Disney",
                "thumbnail_url": "https://img.example/abc.jpg",
            }
        ]

        with patch("app.main.search_videos", new=AsyncMock(return_value=expected)):
            with TestClient(app) as client:
                response = client.get("/api/search", params={"q": "  Frozen  "})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"query": "Frozen", "search_id": 41, "results": expected},
        )
        self.assertEqual(repository.searches[0]["query"], "Frozen")
        self.assertEqual(repository.searches[0]["status"], "success")

    def test_search_rejects_whitespace(self) -> None:
        app.dependency_overrides[get_settings] = make_settings

        with TestClient(app) as client:
            response = client.get("/api/search", params={"q": "   "})

        self.assertEqual(response.status_code, 422)

    def test_history_and_playback_endpoints(self) -> None:
        repository = FakeHistoryRepository()
        app.dependency_overrides[get_history_repository] = lambda: repository

        with TestClient(app) as client:
            playback_response = client.post(
                "/api/playback",
                json={"search_id": 41, "video_id": "abc123"},
            )
            history_response = client.get("/api/history", params={"limit": 5})
            health_response = client.get("/health")

        self.assertEqual(playback_response.status_code, 201)
        self.assertTrue(playback_response.json()["recorded"])
        self.assertEqual(history_response.status_code, 200)
        self.assertTrue(history_response.json()["enabled"])
        self.assertEqual(repository.history_limits, [5])
        self.assertTrue(health_response.json()["database"]["connected"])


class FakeHistoryRepository:
    enabled = True

    def __init__(self) -> None:
        self.searches: list[dict[str, object]] = []
        self.history_limits: list[int] = []

    async def record_search(
        self,
        query: str,
        settings: Settings,
        results: list[dict[str, str]],
        *,
        status: str,
        error_message: str | None = None,
    ) -> int:
        self.searches.append(
            {
                "query": query,
                "results": results,
                "status": status,
                "error_message": error_message,
            }
        )
        return 41

    async def record_playback(
        self, search_id: int, video_id: str
    ) -> dict[str, object] | None:
        if search_id != 41 or video_id != "abc123":
            return None
        return {
            "id": 7,
            "search_id": search_id,
            "video_id": video_id,
            "title": "Libre soy",
        }

    async def recent_history(self, limit: int) -> dict[str, object]:
        self.history_limits.append(limit)
        return {"enabled": True, "searches": [], "playbacks": []}

    async def ping(self) -> bool:
        return True

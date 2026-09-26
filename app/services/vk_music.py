from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class VkMusicError(Exception):
    def __init__(self, message: str, code: int | None = None):
        self.message = message
        self.code = code
        super().__init__(message)


_MOCK_LIBRARY: dict[str, list[dict[str, Any]]] = {}


def _mock_user_id(access_token: str) -> str:
    if not access_token.startswith("mock-access-"):
        return "100001"
    return access_token.removeprefix("mock-access-") or "100001"


def _mock_tracks(user_id: str) -> list[dict[str, Any]]:
    return [
        {
            "owner_id": int(user_id), "id": 1, "artist": "Daft Punk", "title": "Instant Crush",
            "duration": 337, "url": "https://example.com/mock-audio/instant-crush.mp3", "date": 0,
            "access_key": "mock-key-1", "album_id": 101,
        },
        {
            "owner_id": int(user_id), "id": 2, "artist": "M83", "title": "Midnight City",
            "duration": 243, "url": "https://example.com/mock-audio/midnight-city.mp3", "date": 0,
            "access_key": "mock-key-2", "album_id": 102,
        },
        {
            "owner_id": int(user_id), "id": 3, "artist": "The Weeknd", "title": "Blinding Lights",
            "duration": 200, "url": "https://example.com/mock-audio/blinding-lights.mp3", "date": 0,
            "access_key": "mock-key-3", "album_id": 103,
        },
    ]


class VkMusicClient:
    """VK audio adapter with a development mock mode.

    Real mode only forwards API calls. It does not scrape VK pages, replay browser
    cookies, bypass DRM, remove VK advertising, download protected media, or modify
    third-party media streams.
    """

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token
        self.timeout = httpx.Timeout(15.0, connect=10.0)

    async def call(self, method: str, **params: Any) -> dict:
        if settings.vk_mock_mode:
            return self._mock_call(method, **params)

        params = {k: v for k, v in params.items() if v is not None}
        params.update({"access_token": self.access_token, "v": settings.vk_api_version})
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{settings.vk_api_url}/{method}", params=params)
        if response.status_code >= 400:
            raise VkMusicError(f"VK API HTTP {response.status_code}: {response.text}")
        payload = response.json()
        if payload.get("error"):
            error = payload["error"]
            raise VkMusicError(error.get("error_msg", "VK API error"), error.get("error_code"))
        return payload.get("response", {})

    def _mock_call(self, method: str, **params: Any) -> dict:
        user_id = _mock_user_id(self.access_token)
        library = _MOCK_LIBRARY.setdefault(user_id, _mock_tracks(user_id))

        if method == "audio.get":
            offset = int(params.get("offset") or 0)
            count = int(params.get("count") or 100)
            items = library[offset: offset + count]
            return {"count": len(library), "items": items}

        if method == "audio.search":
            q = str(params.get("q") or "").lower().strip()
            results = [t for t in _mock_tracks(user_id) if q in f"{t['artist']} {t['title']}".lower()]
            return {"count": len(results), "items": results}

        if method == "audio.add":
            owner_id = int(params["owner_id"])
            audio_id = int(params["audio_id"])
            existing = next((t for t in _mock_tracks(user_id) if t["owner_id"] == owner_id and t["id"] == audio_id), None)
            if existing and not any(t["owner_id"] == owner_id and t["id"] == audio_id for t in library):
                library.append(existing.copy())
            return {"success": 1}

        if method == "audio.delete":
            owner_id = int(params["owner_id"])
            audio_id = int(params["audio_id"])
            _MOCK_LIBRARY[user_id] = [t for t in library if not (t["owner_id"] == owner_id and t["id"] == audio_id)]
            return {"success": 1}

        if method == "audio.getById":
            raw = str(params.get("audios") or "")
            try:
                owner_id, audio_id = [int(x) for x in raw.split("_", 1)]
            except Exception:
                raise VkMusicError("Invalid mock audio id", 100)
            for track in _mock_tracks(user_id):
                if track["owner_id"] == owner_id and track["id"] == audio_id:
                    return {"items": [track]}
            raise VkMusicError("Track not found", 5)

        raise VkMusicError(f"Unsupported mock method: {method}")

    async def get_library(self, offset: int = 0, count: int = 100) -> dict:
        return await self.call("audio.get", owner_id=None, offset=offset, count=count)

    async def search(self, q: str, offset: int = 0, count: int = 50) -> dict:
        return await self.call("audio.search", q=q, offset=offset, count=count, auto_complete=0)

    async def add(self, owner_id: int, audio_id: int, add_hash: str | None = None) -> dict:
        return await self.call("audio.add", owner_id=owner_id, audio_id=audio_id, hash=add_hash)

    async def delete(self, owner_id: int, audio_id: int, delete_hash: str | None = None) -> dict:
        return await self.call("audio.delete", owner_id=owner_id, audio_id=audio_id, hash=delete_hash)

    async def get_by_id(self, owner_id: int, audio_id: int) -> dict:
        return await self.call("audio.getById", audios=f"{owner_id}_{audio_id}")


def normalize_track(item: dict) -> dict:
    return {
        "owner_id": item.get("owner_id"),
        "id": item.get("id"),
        "artist": item.get("artist"),
        "title": item.get("title"),
        "duration": item.get("duration"),
        "url": item.get("url"),
        "date": item.get("date"),
        "access_key": item.get("access_key"),
        "add_hash": item.get("add_hash") or item.get("hash"),
        "delete_hash": item.get("delete_hash"),
        "album_id": item.get("album_id"),
        "album": item.get("album") if isinstance(item.get("album"), dict) else None,
        "raw": item,
    }

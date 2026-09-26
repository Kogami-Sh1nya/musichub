from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vk_user_id: str
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None


class OAuthStartResponse(BaseModel):
    authorization_url: str


class OAuthExchangeRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=1)


class Track(BaseModel):
    owner_id: int | None = None
    id: int | None = None
    artist: str | None = None
    title: str | None = None
    duration: int | None = None
    url: str | None = None
    date: int | None = None
    access_key: str | None = None
    add_hash: str | None = None
    delete_hash: str | None = None
    album_id: int | None = None
    album: dict | None = None
    raw: dict | None = None


class PaginatedTracks(BaseModel):
    count: int
    items: list[Track]
    offset: int
    limit: int


class MusicSearchResponse(PaginatedTracks):
    query: str


class AddTrackRequest(BaseModel):
    owner_id: int
    audio_id: int
    add_hash: str | None = None


class RemoveTrackQuery(BaseModel):
    delete_hash: str | None = None

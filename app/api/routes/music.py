from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_vk_account
from app.core.security import decrypt_secret, encrypt_secret, utcnow
from app.db import get_db
from app.models import User, VkAccount
from app.schemas import AddTrackRequest, MusicSearchResponse, PaginatedTracks, Track
from app.services.vk_id import VkIdClient, VkIdError
from app.services.vk_music import VkMusicClient, VkMusicError, normalize_track

router = APIRouter(tags=["music"])


async def get_access_token(account: VkAccount, db: AsyncSession) -> str:
    now = utcnow()
    if account.access_expires_at is None or account.access_expires_at > now + timedelta(minutes=1):
        return decrypt_secret(account.access_token_encrypted)

    if not account.refresh_token_encrypted:
        raise HTTPException(status_code=401, detail="VK access token expired and no refresh token is available")

    vk = VkIdClient()
    try:
        payload = await vk.refresh_token(decrypt_secret(account.refresh_token_encrypted), account.device_id)
    except VkIdError as exc:
        raise HTTPException(status_code=502, detail=exc.detail)

    account.access_token_encrypted = encrypt_secret(payload["access_token"])
    if payload.get("refresh_token"):
        account.refresh_token_encrypted = encrypt_secret(payload["refresh_token"])
    account.access_expires_at = vk.access_expiry(payload.get("expires_in"))
    account.refresh_expires_at = vk.refresh_expiry(payload.get("refresh_token_expires_in")) or account.refresh_expires_at
    account.device_id = payload.get("device_id") or account.device_id
    await db.commit()
    return payload["access_token"]


async def music_client(user: User, db: AsyncSession) -> VkMusicClient:
    account = await get_vk_account(user, db)
    return VkMusicClient(await get_access_token(account, db))


@router.get("/library", response_model=PaginatedTracks)
async def library(
    offset: int = Query(ge=0, le=1000000, default=0),
    limit: int = Query(ge=1, le=1000, default=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await music_client(user, db)
    try:
        data = await client.get_library(offset=offset, count=limit)
    except VkMusicError as exc:
        raise HTTPException(status_code=502, detail={"message": exc.message, "vk_error_code": exc.code})
    items = data.get("items", [])
    return PaginatedTracks(count=data.get("count", len(items)), items=[Track(**normalize_track(item)) for item in items], offset=offset, limit=limit)


@router.get("/search", response_model=MusicSearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=200),
    offset: int = Query(ge=0, le=1000000, default=0),
    limit: int = Query(ge=1, le=100, default=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await music_client(user, db)
    try:
        data = await client.search(q=q, offset=offset, count=limit)
    except VkMusicError as exc:
        raise HTTPException(status_code=502, detail={"message": exc.message, "vk_error_code": exc.code})
    items = data.get("items", [])
    return MusicSearchResponse(query=q, count=data.get("count", len(items)), items=[Track(**normalize_track(item)) for item in items], offset=offset, limit=limit)


@router.post("/library/tracks", response_model=Track, status_code=status.HTTP_201_CREATED)
async def add_track(
    payload: AddTrackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await music_client(user, db)
    try:
        await client.add(payload.owner_id, payload.audio_id, payload.add_hash)
        data = await client.get_by_id(payload.owner_id, payload.audio_id)
    except VkMusicError as exc:
        raise HTTPException(status_code=502, detail={"message": exc.message, "vk_error_code": exc.code})
    if isinstance(data, list):
        item = data[0] if data else {"owner_id": payload.owner_id, "id": payload.audio_id}
    else:
        items = data.get("items", []) if isinstance(data, dict) else []
        item = items[0] if items else {"owner_id": payload.owner_id, "id": payload.audio_id}
    return Track(**normalize_track(item))


@router.delete("/library/tracks/{owner_id}/{audio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_track(
    owner_id: int,
    audio_id: int,
    delete_hash: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await music_client(user, db)
    try:
        await client.delete(owner_id, audio_id, delete_hash)
    except VkMusicError as exc:
        raise HTTPException(status_code=502, detail={"message": exc.message, "vk_error_code": exc.code})


@router.get("/tracks/{owner_id}/{audio_id}", response_model=Track)
async def track(
    owner_id: int,
    audio_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await music_client(user, db)
    try:
        data = await client.get_by_id(owner_id, audio_id)
    except VkMusicError as exc:
        raise HTTPException(status_code=502, detail={"message": exc.message, "vk_error_code": exc.code})
    if isinstance(data, list):
        item = data[0] if data else None
    else:
        items = data.get("items", []) if isinstance(data, dict) else []
        item = items[0] if items else None
    if not item:
        raise HTTPException(status_code=404, detail="Track not found")
    return Track(**normalize_track(item))

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_secret,
    encrypt_secret,
    generate_code_verifier,
    generate_state,
    hash_token,
    utcnow,
)
from app.db import get_db
from app.models import OAuthState, RefreshSession, User, VkAccount
from app.schemas import OAuthStartResponse, TokenPair
from app.services.vk_id import VkIdClient, VkIdError

router = APIRouter(prefix="/auth", tags=["auth"])


def token_pair(user_id):
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    return access, refresh


async def persist_refresh_session(db: AsyncSession, user_id, refresh: str) -> None:
    session = RefreshSession(
        user_id=user_id,
        token_hash=hash_token(refresh),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)


@router.get("/vk/start", response_model=OAuthStartResponse)
async def vk_start(db: AsyncSession = Depends(get_db)):
    state = generate_state()
    verifier = generate_code_verifier()
    db.add(
        OAuthState(
            state_hash=hash_token(state),
            code_verifier_encrypted=encrypt_secret(verifier),
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    await db.commit()
    return OAuthStartResponse(authorization_url=VkIdClient().build_authorization_url(state, verifier))


@router.get("/vk/mock-login")
async def vk_mock_login(state: str, user_id: str = "100001"):
    if not settings.vk_mock_mode:
        raise HTTPException(status_code=404, detail="Not found")
    redirect = f"{settings.vk_redirect_uri}?code=mock-{user_id}&state={state}"
    return RedirectResponse(url=redirect, status_code=302)


@router.get("/vk/callback")
async def vk_callback(code: str, state: str, device_id: str | None = None, db: AsyncSession = Depends(get_db)):
    oauth_state = await db.scalar(
        select(OAuthState).where(
            OAuthState.state_hash == hash_token(state),
            OAuthState.expires_at > utcnow(),
        )
    )
    if not oauth_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    verifier = decrypt_secret(oauth_state.code_verifier_encrypted)
    await db.delete(oauth_state)

    client = VkIdClient()
    try:
        token_payload = await client.exchange_code(code, verifier, device_id=device_id)
        user_payload = await client.user_info(token_payload["access_token"])
        vk_user = client.extract_user(user_payload)
    except VkIdError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    account = await db.scalar(select(VkAccount).where(VkAccount.vk_user_id == vk_user["vk_user_id"]))
    if account:
        user = await db.get(User, account.user_id)
    else:
        user = User()
        db.add(user)
        await db.flush()
        account = VkAccount(user_id=user.id, vk_user_id=vk_user["vk_user_id"])
        db.add(account)

    account.email = vk_user["email"]
    account.phone = vk_user["phone"]
    account.first_name = vk_user["first_name"]
    account.last_name = vk_user["last_name"]
    account.avatar_url = vk_user["avatar_url"]
    account.access_token_encrypted = encrypt_secret(token_payload["access_token"])
    account.refresh_token_encrypted = encrypt_secret(token_payload["refresh_token"]) if token_payload.get("refresh_token") else None
    account.access_expires_at = client.access_expiry(token_payload.get("expires_in"))
    account.refresh_expires_at = client.refresh_expiry(token_payload.get("refresh_token_expires_in"))
    account.device_id = token_payload.get("device_id")
    account.scope = " ".join(token_payload.get("scope", settings.vk_scopes).split())

    access, refresh = token_pair(user.id)
    await persist_refresh_session(db, user.id, refresh)
    await db.commit()

    redirect = RedirectResponse(url=f"{settings.frontend_public_url}/auth/callback", status_code=302)
    redirect.set_cookie("musichub_access_token", access, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.access_token_expire_minutes * 60)
    redirect.set_cookie("musichub_refresh_token", refresh, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.refresh_token_expire_days * 86400)
    return redirect


@router.post("/refresh", response_model=TokenPair)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("musichub_refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token cookie")
    try:
        user_id = jwt.decode(refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]).get("sub")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    session = await db.scalar(
        select(RefreshSession).where(
            RefreshSession.user_id == user_id,
            RefreshSession.token_hash == hash_token(refresh_token),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > utcnow(),
        )
    )
    if not session:
        raise HTTPException(status_code=401, detail="Refresh session is invalid or expired")

    session.revoked_at = utcnow()
    access, new_refresh = token_pair(session.user_id)
    await persist_refresh_session(db, session.user_id, new_refresh)
    await db.commit()

    response.set_cookie("musichub_access_token", access, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.access_token_expire_minutes * 60)
    response.set_cookie("musichub_refresh_token", new_refresh, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.refresh_token_expire_days * 86400)
    return TokenPair(access_token=access, refresh_token=new_refresh, expires_in=settings.access_token_expire_minutes * 60)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("musichub_refresh_token")
    if refresh_token:
        session = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == hash_token(refresh_token)))
        if session:
            session.revoked_at = utcnow()
            await db.commit()
    response.delete_cookie("musichub_access_token")
    response.delete_cookie("musichub_refresh_token")

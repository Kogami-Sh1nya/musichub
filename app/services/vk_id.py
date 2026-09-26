from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import settings


class VkIdError(Exception):
    def __init__(self, detail: str, status_code: int = 502):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class VkIdClient:
    def __init__(self) -> None:
        self.timeout = httpx.Timeout(15.0, connect=10.0)

    def build_authorization_url(self, state: str, code_verifier: str) -> str:
        if settings.vk_mock_mode:
            query = {"state": state, "user_id": "100001"}
            return f"{settings.backend_public_url}/api/v1/auth/vk/mock-login?{urlencode(query)}"

        query = {
            "response_type": "code",
            "client_id": settings.vk_client_id,
            "redirect_uri": settings.vk_redirect_uri,
            "state": state,
            "code_challenge": self._challenge(code_verifier),
            "code_challenge_method": "S256",
            "scope": " ".join(settings.vk_scope_list),
        }
        return f"{settings.vk_auth_url}?{urlencode(query)}"

    @staticmethod
    def _challenge(verifier: str) -> str:
        from app.core.security import pkce_challenge
        return pkce_challenge(verifier)

    async def exchange_code(self, code: str, code_verifier: str, device_id: str | None = None) -> dict:
        if settings.vk_mock_mode and code.startswith("mock-"):
            vk_user_id = code.removeprefix("mock-") or "100001"
            return {
                "access_token": f"mock-access-{vk_user_id}",
                "refresh_token": f"mock-refresh-{vk_user_id}",
                "expires_in": 3600,
                "refresh_token_expires_in": 86400,
                "device_id": device_id or "mock-device",
                "scope": settings.vk_scopes,
            }

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.vk_client_id,
            "redirect_uri": settings.vk_redirect_uri,
            "code_verifier": code_verifier,
        }
        if device_id:
            data["device_id"] = device_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(settings.vk_token_url, data=data)
        if response.status_code >= 400:
            raise VkIdError(f"VK ID token exchange failed: {response.text}")
        payload = response.json()
        if payload.get("error"):
            raise VkIdError(f"VK ID token exchange error: {payload.get('error_description') or payload['error']}")
        if not payload.get("access_token"):
            raise VkIdError("VK ID returned no access token")
        return payload

    async def refresh_token(self, refresh_token: str, device_id: str | None) -> dict:
        if settings.vk_mock_mode and refresh_token.startswith("mock-refresh-"):
            vk_user_id = refresh_token.removeprefix("mock-refresh-") or "100001"
            return {
                "access_token": f"mock-access-{vk_user_id}",
                "refresh_token": refresh_token,
                "expires_in": 3600,
                "refresh_token_expires_in": 86400,
                "device_id": device_id or "mock-device",
            }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.vk_client_id,
        }
        if device_id:
            data["device_id"] = device_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(settings.vk_token_url, data=data)
        if response.status_code >= 400:
            raise VkIdError(f"VK ID refresh failed: {response.text}")
        payload = response.json()
        if payload.get("error") or not payload.get("access_token"):
            raise VkIdError(f"VK ID refresh error: {payload.get('error_description') or payload.get('error', 'unknown error')}")
        return payload

    async def user_info(self, access_token: str) -> dict:
        if settings.vk_mock_mode and access_token.startswith("mock-access-"):
            vk_user_id = access_token.removeprefix("mock-access-") or "100001"
            return {
                "user": {
                    "user_id": vk_user_id,
                    "email": f"dev{vk_user_id}@example.local",
                    "phone": "+70000000000",
                    "first_name": "MusicHub",
                    "last_name": "Developer",
                    "avatar": "https://dummyimage.com/256x256/cccccc/000000&text=MH",
                }
            }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                settings.vk_userinfo_url,
                params={"client_id": settings.vk_client_id},
                data={"access_token": access_token},
            )
        if response.status_code >= 400:
            raise VkIdError(f"VK ID user_info failed: {response.text}")
        payload = response.json()
        if payload.get("error"):
            raise VkIdError(f"VK ID user_info error: {payload.get('error_description') or payload['error']}")
        return payload

    @staticmethod
    def extract_user(payload: dict) -> dict:
        user = payload.get("user") if isinstance(payload.get("user"), dict) else payload
        vk_user_id = user.get("user_id") or payload.get("user_id")
        if not vk_user_id:
            raise VkIdError("VK ID user_info response does not contain user_id")
        return {
            "vk_user_id": str(vk_user_id),
            "email": user.get("email"),
            "phone": user.get("phone"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "avatar_url": user.get("avatar"),
        }

    @staticmethod
    def access_expiry(expires_in: int | None) -> datetime | None:
        if not expires_in:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    @staticmethod
    def refresh_expiry(expires_in: int | None) -> datetime | None:
        if not expires_in:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

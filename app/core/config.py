from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MusicHub API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    database_url: str = Field(default="postgresql+asyncpg://musichub:musichub@db:5432/musichub", alias="DATABASE_URL")

    jwt_secret_key: str = Field(default="dev-only-change-this-secret", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    token_encryption_key: str = Field(default="umw1sK25PNi-n8-rePoz9d5bt-rlmcJvxSt1yz61km4=", alias="TOKEN_ENCRYPTION_KEY")

    backend_public_url: str = "http://localhost:8000"
    frontend_public_url: str = "http://localhost:3000"

    vk_mock_mode: bool = True
    vk_client_id: str = Field(default="dev-client", alias="VK_CLIENT_ID")
    vk_redirect_uri: str = Field(default="http://localhost:8000/api/v1/auth/vk/callback", alias="VK_REDIRECT_URI")
    vk_scopes: str = "vkid.personal_info email phone"
    vk_auth_url: str = "https://id.vk.ru/authorize"
    vk_token_url: str = "https://id.vk.ru/oauth2/auth"
    vk_userinfo_url: str = "https://id.vk.ru/oauth2/user_info"
    vk_api_url: str = "https://api.vk.com/method"
    vk_api_version: str = "5.199"

    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    @property
    def vk_scope_list(self) -> list[str]:
        return [part for part in self.vk_scopes.split() if part]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

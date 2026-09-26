import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "umw1sK25PNi-n8-rePoz9d5bt-rlmcJvxSt1yz61km4=")
os.environ.setdefault("VK_CLIENT_ID", "1")
os.environ.setdefault("VK_REDIRECT_URI", "http://localhost/callback")

from app.core.security import pkce_challenge


def test_pkce_challenge_is_deterministic():
    assert pkce_challenge("abc") == "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0"

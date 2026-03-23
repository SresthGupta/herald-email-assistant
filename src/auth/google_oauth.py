import json
import time
from urllib.parse import urlencode
import httpx
from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GMAIL_SCOPES,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def get_auth_url(state: str = "") -> str:
    """Generate the Google OAuth2 authorization URL."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange an authorization code for access and refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh token to get a new access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return response.json()


async def get_user_info(access_token: str) -> dict:
    """Get the authenticated user's Google profile information."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def calculate_token_expiry(expires_in: int) -> str:
    """Calculate token expiry timestamp."""
    expiry = time.time() + expires_in - 60  # 60s buffer
    return str(expiry)


def is_token_expired(token_expiry: str) -> bool:
    """Check if an access token has expired."""
    try:
        return time.time() >= float(token_expiry)
    except (TypeError, ValueError):
        return True

"""
Authentication service — Google OAuth flow and JWT management.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import User


# ── JWT Token Management ──

def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """Create a JWT access token. Returns (token, expires_in_seconds)."""
    expires_delta = timedelta(days=settings.JWT_EXPIRE_DAYS)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, int(expires_delta.total_seconds())


# ── Google OAuth ──

def get_google_auth_url() -> str:
    """Build the Google OAuth 2.0 authorization URL."""
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(settings.GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{query}"


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for Google OAuth tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def get_google_user_info(access_token: str) -> dict:
    """Fetch user profile info from Google."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


async def upsert_user(
    db: AsyncSession,
    google_id: str,
    email: str,
    name: Optional[str],
    avatar_url: Optional[str],
    access_token: str,
    refresh_token: Optional[str],
    token_expiry: Optional[datetime],
) -> User:
    """Create or update a user from Google OAuth data."""
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            google_access_token=access_token,
            google_refresh_token=refresh_token,
            google_token_expiry=token_expiry,
        )
        db.add(user)
    else:
        user.email = email
        user.name = name
        user.avatar_url = avatar_url
        user.google_access_token = access_token
        if refresh_token:
            user.google_refresh_token = refresh_token
        user.google_token_expiry = token_expiry
        user.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(user)
    return user


async def refresh_google_token(user: User, db: AsyncSession) -> Optional[str]:
    """Refresh the user's Google access token using the stored refresh token."""
    if not user.google_refresh_token:
        return None

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": user.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code != 200:
            return None

        data = response.json()
        user.google_access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        user.google_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        user.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return user.google_access_token


async def get_valid_google_token(user: User, db: AsyncSession) -> Optional[str]:
    """Get a valid Google access token, refreshing if expired."""
    if user.google_token_expiry and user.google_token_expiry > datetime.now(timezone.utc):
        return user.google_access_token
    return await refresh_google_token(user, db)

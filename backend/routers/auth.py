"""
Authentication router — Google OAuth login/callback, user info.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.user import UserResponse
from services.auth import (
    create_access_token,
    exchange_code_for_tokens,
    get_google_auth_url,
    get_google_user_info,
    upsert_user,
)

router = APIRouter()


@router.get("/google/login")
async def google_login():
    """Redirect user to Google OAuth consent page."""
    auth_url = get_google_auth_url()
    return {"authorization_url": auth_url}


@router.get("/google/callback")
async def google_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback.
    Exchange code for tokens, upsert user, redirect to frontend with JWT.
    """
    try:
        # Exchange code for tokens
        token_data = await exchange_code_for_tokens(code)
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        # Get user info from Google
        user_info = await get_google_user_info(access_token)
        google_id = user_info["id"]
        email = user_info["email"]
        name = user_info.get("name")
        avatar_url = user_info.get("picture")

        # Calculate token expiry
        token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Create or update user
        user = await upsert_user(
            db=db,
            google_id=google_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
        )

        # Create JWT
        jwt_token, jwt_expires = create_access_token(user.id)

        # Redirect to frontend with token
        frontend_url = f"{settings.FRONTEND_URL}/auth/callback?token={jwt_token}"
        return RedirectResponse(url=frontend_url)

    except Exception as e:
        # Redirect to frontend with error
        error_url = f"{settings.FRONTEND_URL}/auth/callback?error={str(e)}"
        return RedirectResponse(url=error_url)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user

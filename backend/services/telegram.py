"""
Telegram Bot service — sending messages and handling webhook updates.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import User

TELEGRAM_API = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


async def send_telegram_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            },
        )
        return response.status_code == 200


async def set_telegram_webhook(webhook_url: str) -> bool:
    """Register the webhook URL with Telegram."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
            },
        )
        return response.status_code == 200


async def delete_telegram_webhook() -> bool:
    """Remove the Telegram webhook."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API}/deleteWebhook",
        )
        return response.status_code == 200


async def handle_telegram_start(
    db: AsyncSession,
    chat_id: int,
    username: Optional[str],
    link_token_str: Optional[str],
) -> str:
    """
    Handle the /start command with an optional link token.
    Links the Telegram chat to the user's SheetNotify account.
    """
    if not link_token_str:
        return (
            "👋 Welcome to SheetNotify Bot!\n\n"
            "To link your account, use the link from your SheetNotify dashboard.\n"
            "It will look like:\n"
            "/start <your-link-token>"
        )

    try:
        link_token = uuid.UUID(link_token_str)
    except ValueError:
        return "❌ Invalid link token format. Please use the link from your dashboard."

    # Find user by link token
    result = await db.execute(
        select(User).where(User.telegram_link_token == link_token)
    )
    user = result.scalar_one_or_none()

    if user is None:
        return "❌ Link token not found. Please generate a new link from your dashboard."

    if user.telegram_chat_id is not None and user.telegram_chat_id != chat_id:
        return (
            "⚠️ Your SheetNotify account is already linked to another Telegram account.\n"
            "Please unlink first from your dashboard."
        )

    # Link the account
    user.telegram_chat_id = chat_id
    user.telegram_username = username
    user.telegram_linked_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    # Regenerate link token after use
    user.telegram_link_token = uuid.uuid4()
    await db.flush()

    return (
        f"✅ Successfully linked!\n\n"
        f"Account: {user.email}\n"
        f"You will now receive notifications when new data is added to your monitored Google Sheets."
    )


def get_telegram_link_url(link_token: uuid.UUID, bot_username: str) -> str:
    """Generate the Telegram deep link URL for account linking."""
    return f"https://t.me/{bot_username}?start={link_token}"

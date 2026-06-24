"""
Telegram router — bot webhook, link URL generation.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from config import settings
from database import get_db
from middleware.auth import get_current_user
from models.user import User
from services.telegram import (
    handle_telegram_start,
    get_telegram_link_url,
    send_telegram_message,
    set_telegram_webhook,
)
from services.runtime_urls import resolve_backend_url

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    """
    Receive updates from Telegram Bot API.
    This endpoint is called by Telegram whenever the bot receives a message.
    """
    # Verify webhook secret
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        body = await request.json()
    except Exception:
        logger.exception("Invalid Telegram webhook payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    message = body.get("message", {})
    text = message.get("text", "")
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    username = chat.get("username")

    if not chat_id:
        return {"ok": True}

    # Handle /start command
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        link_token = parts[1] if len(parts) > 1 else None
        reply = await handle_telegram_start(db, chat_id, username, link_token)
        success = await send_telegram_message(chat_id, reply)
        if not success:
            logger.error("Failed to send /start reply to Telegram chat %s", chat_id)
    elif text == "/help":
        success = await send_telegram_message(
            chat_id,
            "🔔 <b>SheetNotify Bot</b>\n\n"
            "I send you notifications when new data is added to your Google Sheets.\n\n"
            "To get started:\n"
            "1. Sign up at SheetNotify\n"
            "2. Link your Telegram from the dashboard\n"
            "3. Connect your Google Sheets\n\n"
            "Commands:\n"
            "/start - Link your account\n"
            "/help - Show this help message",
        )
        if not success:
            logger.error("Failed to send /help reply to Telegram chat %s", chat_id)

    return {"ok": True}


@router.get("/link-url")
async def get_link_url(
    current_user: User = Depends(get_current_user),
):
    """Generate a Telegram deep link URL for the current user to link their account."""
    # Use a hardcoded bot username or derive from settings
    bot_username = settings.TELEGRAM_BOT_USERNAME
    url = get_telegram_link_url(current_user.telegram_link_token, bot_username)
    return {"link_url": url, "bot_username": bot_username}


@router.post("/setup-webhook")
async def setup_webhook(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Set up the Telegram webhook (admin action).
    Only needs to be called once during deployment.
    """
    backend_url = resolve_backend_url(request)
    webhook_url = f"{backend_url}/api/telegram/webhook"
    success = await set_telegram_webhook(webhook_url)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set Telegram webhook")
    return {"status": "ok", "webhook_url": webhook_url}


@router.post("/unlink")
async def unlink_telegram(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink Telegram account from the current user."""
    import uuid
    from datetime import datetime, timezone

    current_user.telegram_chat_id = None
    current_user.telegram_username = None
    current_user.telegram_linked_at = None
    current_user.telegram_link_token = uuid.uuid4()
    current_user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "ok", "message": "Telegram unlinked successfully"}

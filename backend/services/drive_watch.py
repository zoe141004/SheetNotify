"""
Google Drive push-notification (watch channel) management.

Drive notifications are a *trigger only*: the payload never says which cells
changed, just that the file changed. So a notification simply causes us to run
the shared snapshot-diff engine for the affected subscriptions — exactly like
the poller, but near real-time and with no per-user setup (the channel is
created by the backend using the user's OAuth token).

Lifecycle:
  * ``ensure_channel`` — create/reuse a watch for a (user, spreadsheet).
  * ``stop_channel``   — stop a watch (on unsubscribe / cleanup).
  * ``run_drive_maintenance_loop`` — periodically renew channels near expiry,
    because Drive channels expire (max 1 day) and do not auto-renew.

NOTE: Drive only delivers to a domain-verified HTTPS endpoint. ``*.run.app``
cannot be verified, so a custom domain is required for this to work. Everything
here is a no-op unless ``settings.ENABLE_DRIVE_WEBHOOK`` is true.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from datetime import datetime, timezone

import asyncio
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session
from models.drive_channel import DriveWatchChannel
from models.subscription import SheetSubscription
from models.user import User
from services.auth import get_valid_google_token
from services.runtime_urls import resolve_backend_url

logger = logging.getLogger(__name__)


def _drive_webhook_address(request=None) -> str | None:
    """Resolve the public callback URL, or None if no public URL is available."""
    try:
        base = resolve_backend_url(request)
    except Exception:
        return None
    if base.startswith("http://"):  # Drive requires HTTPS
        return None
    return f"{base}/api/webhook/drive"


async def _watch_file(
    access_token: str,
    file_id: str,
    channel_id: str,
    token: str,
    address: str,
    ttl_seconds: int,
) -> dict | None:
    expiration_ms = int((time.time() + ttl_seconds) * 1000)
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": address,
        "token": token,
        "expiration": str(expiration_ms),
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/watch",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
    if response.status_code not in (200, 201):
        logger.warning(
            "Drive watch failed for file %s: HTTP %s %s",
            file_id,
            response.status_code,
            response.text,
        )
        return None
    return response.json()


async def _stop_channel_api(access_token: str, channel_id: str, resource_id: str) -> bool:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://www.googleapis.com/drive/v3/channels/stop",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"id": channel_id, "resourceId": resource_id},
        )
    return response.status_code in (200, 204)


def _parse_expiration(payload: dict) -> datetime | None:
    raw = payload.get("expiration")
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


async def ensure_channel(
    session: AsyncSession,
    user: User,
    spreadsheet_id: str,
    request=None,
) -> DriveWatchChannel | None:
    """Create or reuse a Drive watch channel for a (user, spreadsheet).

    Returns the channel, or None if Drive webhooks are disabled / unavailable
    (in which case polling remains the safety net). Never raises — failures are
    logged and degrade gracefully to polling.
    """
    if not settings.ENABLE_DRIVE_WEBHOOK:
        return None

    address = _drive_webhook_address(request)
    if not address:
        logger.warning("Drive webhook enabled but no public HTTPS BACKEND_URL — skipping watch")
        return None

    existing = (
        await session.execute(
            select(DriveWatchChannel).where(
                DriveWatchChannel.user_id == user.id,
                DriveWatchChannel.spreadsheet_id == spreadsheet_id,
            )
        )
    ).scalar_one_or_none()

    # Reuse a channel that still has comfortable runway.
    if existing is not None and existing.expiration is not None:
        remaining = (existing.expiration - datetime.now(timezone.utc)).total_seconds()
        if remaining > settings.DRIVE_CHANNEL_RENEW_BEFORE_SECONDS:
            return existing

    access_token = await get_valid_google_token(user, session)
    if not access_token:
        logger.warning("No Google token to create Drive watch for user %s", user.id)
        return None

    channel_id = uuid.uuid4().hex
    token = secrets.token_hex(16)
    result = await _watch_file(
        access_token,
        spreadsheet_id,
        channel_id,
        token,
        address,
        settings.DRIVE_WEBHOOK_TTL_SECONDS,
    )
    if result is None:
        return None

    # Stop the previous channel (best-effort) before replacing it.
    if existing is not None and existing.resource_id:
        await _stop_channel_api(access_token, existing.channel_id, existing.resource_id)

    if existing is None:
        existing = DriveWatchChannel(
            user_id=user.id,
            spreadsheet_id=spreadsheet_id,
            channel_id=channel_id,
            channel_token=token,
        )
        session.add(existing)
    else:
        existing.channel_id = channel_id
        existing.channel_token = token

    existing.resource_id = result.get("resourceId")
    existing.expiration = _parse_expiration(result)
    await session.flush()
    return existing


async def stop_channel(session: AsyncSession, channel: DriveWatchChannel, user: User) -> None:
    """Stop and delete a watch channel (best-effort)."""
    access_token = await get_valid_google_token(user, session)
    if access_token and channel.resource_id:
        await _stop_channel_api(access_token, channel.channel_id, channel.resource_id)
    await session.delete(channel)
    await session.flush()


async def cleanup_spreadsheet_channel_if_unused(
    session: AsyncSession, user: User, spreadsheet_id: str
) -> None:
    """Remove the Drive channel for a spreadsheet if no subscriptions remain."""
    if not settings.ENABLE_DRIVE_WEBHOOK:
        return
    remaining = (
        await session.execute(
            select(SheetSubscription.id).where(
                SheetSubscription.user_id == user.id,
                SheetSubscription.spreadsheet_id == spreadsheet_id,
            ).limit(1)
        )
    ).first()
    if remaining is not None:
        return
    channel = (
        await session.execute(
            select(DriveWatchChannel).where(
                DriveWatchChannel.user_id == user.id,
                DriveWatchChannel.spreadsheet_id == spreadsheet_id,
            )
        )
    ).scalar_one_or_none()
    if channel is not None:
        await stop_channel(session, channel, user)


async def _renew_expiring_channels() -> None:
    cutoff = datetime.now(timezone.utc).timestamp() + settings.DRIVE_CHANNEL_RENEW_BEFORE_SECONDS
    async with async_session() as session:
        channels = list(
            (
                await session.execute(select(DriveWatchChannel))
            ).scalars().all()
        )
        for channel in channels:
            if channel.expiration is not None and channel.expiration.timestamp() > cutoff:
                continue
            user = (
                await session.execute(select(User).where(User.id == channel.user_id))
            ).scalar_one_or_none()
            if user is None:
                continue
            try:
                await ensure_channel(session, user, channel.spreadsheet_id)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("Failed to renew Drive channel %s", channel.channel_id)


async def run_drive_maintenance_loop() -> None:
    """Periodically renew Drive channels before they expire."""
    while True:
        try:
            await _renew_expiring_channels()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Drive maintenance loop iteration failed")
        await asyncio.sleep(settings.DRIVE_MAINTENANCE_CYCLE_SECONDS)

"""
Webhook router — receives change triggers from external sources.

Two trigger sources funnel into the same shared snapshot-diff engine:
  * POST /{webhook_secret}  → Google Apps Script (optional, power users)
  * POST /drive             → Google Drive push notification (near real-time)

Both are treated purely as a "something changed" signal: the backend re-reads
the sheet and diffs it against the stored snapshot. The Drive payload itself is
empty, so no body is trusted.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.change_processor import process_drive_notification, process_webhook

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/drive")
async def receive_drive_notification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_goog_channel_id: Optional[str] = Header(None),
    x_goog_channel_token: Optional[str] = Header(None),
    x_goog_resource_state: Optional[str] = Header(None),
):
    """Receive a Google Drive push notification (file changed)."""
    # The very first message after creating a channel is a "sync" handshake.
    if x_goog_resource_state == "sync":
        return {"ok": True}
    if not x_goog_channel_id:
        return {"ok": True}

    try:
        await process_drive_notification(db, x_goog_channel_id, x_goog_channel_token)
    except Exception:
        # Always return 200 for non-5xx so Drive doesn't hammer us with retries
        # on a permanent error; the maintenance/poll backstop will recover.
        logger.exception("Drive notification handling failed for channel %s", x_goog_channel_id)

    return {"ok": True}


@router.post("/{webhook_secret}")
async def receive_webhook(
    webhook_secret: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive a webhook trigger from Google Apps Script.
    The webhook_secret path parameter authenticates the request.
    """
    # Body is accepted but not trusted — the engine re-reads the sheet itself.
    try:
        await request.json()
    except Exception:
        pass

    return await process_webhook(db, webhook_secret)

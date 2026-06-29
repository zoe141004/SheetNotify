"""
Background polling service for Google Sheets change detection.

This is the *default, zero-setup* trigger: every cycle it wakes up and asks the
shared change-processing engine to pull each active subscription's data and diff
it against the stored snapshot. The actual detection/notification logic lives in
:mod:`services.change_processor` and is shared with the Apps Script webhook path.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from database import async_session
from models.subscription import SheetSubscription
from services.change_processor import process_subscription_changes

logger = logging.getLogger(__name__)


async def poll_subscription(subscription_id) -> None:
    async with async_session() as session:
        try:
            await process_subscription_changes(
                session,
                subscription_id,
                detection_method="polling",
                respect_interval=True,
                require_polling_enabled=True,
            )
        except Exception:
            await session.rollback()
            logger.exception("Polling failed for subscription %s", subscription_id)


async def run_poll_cycle() -> int:
    """Run ONE polling pass over all active polling-enabled subscriptions.

    Returns the number of subscriptions processed. Used by both the in-process
    loop (always-on mode) and the Cloud Scheduler endpoint (free scale-to-zero
    mode), so polling works without keeping an instance running 24/7.
    """
    async with async_session() as session:
        result = await session.execute(
            select(SheetSubscription.id).where(
                SheetSubscription.is_active.is_(True),
                SheetSubscription.polling_enabled.is_(True),
            )
        )
        subscription_ids = list(result.scalars().all())

    for subscription_id in subscription_ids:
        await poll_subscription(subscription_id)
    return len(subscription_ids)


async def run_polling_loop(poll_interval_seconds: int = 60) -> None:
    """Continuously poll (always-on mode). Free mode uses run_poll_cycle via Scheduler."""
    while True:
        try:
            await run_poll_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Polling loop iteration failed")

        await asyncio.sleep(poll_interval_seconds)

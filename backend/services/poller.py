"""
Background polling service for Google Sheets change detection.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database import async_session
from models.notification import NotificationLog
from models.subscription import SheetSubscription
from models.user import User
from services.change_detector import detect_changes, snapshot_rows
from services.notification import format_polling_notification
from services.sheets import get_sheet_snapshot, get_spreadsheet_snapshots
from services.telegram import send_telegram_message

logger = logging.getLogger(__name__)


def _normalize_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return snapshot or {"sheets": {}}


async def _load_subscription_bundle(session, subscription_id):
    subscription_result = await session.execute(
        select(SheetSubscription).where(SheetSubscription.id == subscription_id)
    )
    subscription = subscription_result.scalar_one_or_none()
    if subscription is None:
        return None, None

    user_result = await session.execute(select(User).where(User.id == subscription.user_id))
    user = user_result.scalar_one_or_none()
    return subscription, user


async def poll_subscription(subscription_id) -> None:
    async with async_session() as session:
        subscription, user = await _load_subscription_bundle(session, subscription_id)
        if subscription is None or user is None:
            return

        if not subscription.is_active or not subscription.polling_enabled:
            return

        if subscription.last_polled_at is not None:
            elapsed_seconds = (
                datetime.now(timezone.utc) - subscription.last_polled_at
            ).total_seconds()
            minimum_interval = max(int(subscription.polling_interval_minutes or 1), 1) * 60
            if elapsed_seconds < minimum_interval:
                return

        try:
            if subscription.track_all_sheets:
                snapshots = await get_spreadsheet_snapshots(
                    user,
                    session,
                    subscription.spreadsheet_id,
                    subscription.monitored_sheet_names,
                )
            else:
                single_snapshot = await get_sheet_snapshot(
                    user,
                    session,
                    subscription.spreadsheet_id,
                    subscription.sheet_name,
                )
                snapshots = [single_snapshot] if single_snapshot is not None else []

            previous_state = _normalize_snapshot(subscription.last_state_snapshot)
            current_state: dict[str, Any] = {"sheets": {}}
            all_changes = []

            for snapshot in snapshots:
                current_state["sheets"][snapshot.sheet_name] = snapshot_rows(
                    snapshot.rows,
                    snapshot.headers,
                )
                previous_sheet_state = previous_state.get("sheets", {}).get(snapshot.sheet_name, {})
                previous_rows = previous_sheet_state.get("rows", [])
                changes = detect_changes(previous_rows, snapshot.rows, snapshot.headers)
                for change in changes:
                    all_changes.append((snapshot, change))

            if not all_changes:
                subscription.last_state_snapshot = current_state
                subscription.last_polled_at = datetime.now(timezone.utc)
                subscription.last_poll_error = None
                subscription.poll_failure_count = 0
                await session.commit()
                return

            for snapshot, change in all_changes:
                message = format_polling_notification(
                    spreadsheet_name=snapshot.spreadsheet_name,
                    sheet_name=snapshot.sheet_name,
                    change_type=change.change_type,
                    row_number=change.row_number,
                    changed_columns=change.changed_columns,
                    before_data=change.before,
                    after_data=change.after,
                    cell_reference=change.cell_reference,
                )
                success = await send_telegram_message(user.telegram_chat_id, message)

                log = NotificationLog(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    spreadsheet_id=snapshot.spreadsheet_id,
                    spreadsheet_name=snapshot.spreadsheet_name,
                    sheet_name=snapshot.sheet_name,
                    row_number=change.row_number,
                    row_data=change.after or change.before or {},
                    before_data=change.before,
                    after_data=change.after,
                    changed_columns=change.changed_columns,
                    cell_reference=change.cell_reference,
                    change_type=change.change_type,
                    detection_method="polling",
                    telegram_message=message,
                    status="sent" if success else "failed",
                    error_message=None if success else "Failed to send Telegram message",
                    sent_at=datetime.now(timezone.utc) if success else None,
                )
                session.add(log)

            subscription.last_state_snapshot = current_state
            subscription.last_polled_at = datetime.now(timezone.utc)
            subscription.last_poll_error = None
            subscription.poll_failure_count = 0
            await session.commit()
        except Exception as exc:
            subscription.last_poll_error = str(exc)
            subscription.poll_failure_count = (subscription.poll_failure_count or 0) + 1
            subscription.last_polled_at = datetime.now(timezone.utc)
            await session.commit()
            logger.exception("Polling failed for subscription %s", subscription_id)


async def run_polling_loop(poll_interval_seconds: int = 60) -> None:
    """Continuously poll all active polling-enabled subscriptions."""
    while True:
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

        await asyncio.sleep(poll_interval_seconds)
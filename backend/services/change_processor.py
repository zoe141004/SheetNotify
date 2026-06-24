"""
Shared change-processing engine.

Both the background poller (timer trigger) and the Apps Script webhook (real-time
trigger) funnel through :func:`process_subscription_changes`. The trigger only
decides *when* to run — the actual work is always the same:

    1. Acquire a PostgreSQL advisory lock for the subscription so that at most
       one worker processes it at a time. This makes the operation safe across
       multiple Cloud Run instances *and* removes the webhook-vs-poller race
       (Tasks 3 & 4 in SYSTEM_STATUS). If the lock cannot be acquired we assume
       another worker is already handling it and return immediately.
    2. Pull the *full* current data of the sheet(s) via the Google Sheets API.
    3. Diff it against the snapshot stored in PostgreSQL (content-based).
    4. Send a Telegram notification per change and persist a notification log.
    5. Persist the new snapshot atomically in the same transaction.

Because the snapshot is updated inside the locked transaction, a duplicate
trigger (e.g. webhook + poller firing close together) simply finds no diff the
second time — the design is naturally idempotent.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import NotificationLog
from models.subscription import SheetSubscription
from models.user import User
from services.change_detector import detect_changes, snapshot_rows
from services.notification import describe_change, format_changes_message
from services.sheets import get_sheet_snapshot, get_spreadsheet_snapshots
from services.telegram import send_telegram_message

logger = logging.getLogger(__name__)


def _normalize_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return snapshot or {"sheets": {}}


def _advisory_lock_key(subscription_id: Any) -> int:
    """Derive a stable 63-bit positive bigint key from a subscription UUID."""
    return uuid.UUID(str(subscription_id)).int & ((1 << 63) - 1)


async def _try_advisory_lock(session: AsyncSession, subscription_id: Any) -> bool:
    result = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": _advisory_lock_key(subscription_id)},
    )
    return bool(result.scalar())


async def process_subscription_changes(
    session: AsyncSession,
    subscription_id: Any,
    *,
    detection_method: str,
    respect_interval: bool,
    require_polling_enabled: bool,
) -> dict[str, Any]:
    """Pull the latest sheet data, diff against the snapshot, and notify.

    Returns a small status dict (handy for the webhook response). All database
    work is committed/rolled back here so callers do not need to manage the
    transaction.
    """
    # Serialize processing per-subscription across workers/instances.
    if not await _try_advisory_lock(session, subscription_id):
        return {"status": "skipped", "message": "Another worker is processing this subscription"}

    subscription = (
        await session.execute(
            select(SheetSubscription).where(SheetSubscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    if subscription is None:
        return {"status": "error", "message": "Subscription not found"}

    user = (
        await session.execute(select(User).where(User.id == subscription.user_id))
    ).scalar_one_or_none()
    if user is None:
        return {"status": "error", "message": "User not found"}

    if not subscription.is_active:
        return {"status": "skipped", "message": "Subscription inactive"}
    if require_polling_enabled and not subscription.polling_enabled:
        return {"status": "skipped", "message": "Polling disabled"}

    now = datetime.now(timezone.utc)

    if respect_interval and subscription.last_polled_at is not None:
        elapsed = (now - subscription.last_polled_at).total_seconds()
        minimum_interval = max(int(subscription.polling_interval_minutes or 1), 1) * 60
        if elapsed < minimum_interval:
            return {"status": "skipped", "message": "Polling interval not elapsed"}

    try:
        if subscription.track_all_sheets:
            snapshots = await get_spreadsheet_snapshots(
                user,
                session,
                subscription.spreadsheet_id,
                subscription.monitored_sheet_names,
            )
        else:
            single = await get_sheet_snapshot(
                user,
                session,
                subscription.spreadsheet_id,
                subscription.sheet_name,
            )
            snapshots = [single] if single is not None else []
    except Exception as exc:  # network / API error
        subscription.last_poll_error = str(exc)
        subscription.poll_failure_count = (subscription.poll_failure_count or 0) + 1
        subscription.last_polled_at = now
        await session.commit()
        logger.exception("Failed to fetch sheet data for subscription %s", subscription_id)
        return {"status": "failed", "message": "Failed to fetch sheet data"}

    if not snapshots:
        # Could not read the sheet (revoked token, lost access, etc.). Record the
        # error but DO NOT overwrite the stored snapshot, otherwise the next
        # successful poll would treat every existing row as brand new.
        subscription.last_poll_error = "Unable to fetch sheet data (no access or empty response)"
        subscription.poll_failure_count = (subscription.poll_failure_count or 0) + 1
        subscription.last_polled_at = now
        await session.commit()
        return {"status": "failed", "message": "Unable to fetch sheet data"}

    previous_state = _normalize_snapshot(subscription.last_state_snapshot)
    current_state: dict[str, Any] = {"sheets": {}}
    is_baseline = subscription.last_state_snapshot is None

    all_changes: list[tuple[Any, Any]] = []
    for snapshot in snapshots:
        current_state["sheets"][snapshot.sheet_name] = snapshot_rows(
            snapshot.rows, snapshot.headers
        )
        if is_baseline:
            continue
        previous_sheet = previous_state.get("sheets", {}).get(snapshot.sheet_name, {})
        previous_rows = previous_sheet.get("rows", [])
        previous_headers = previous_sheet.get("headers")
        for change in detect_changes(
            previous_rows, snapshot.rows, snapshot.headers, previous_headers
        ):
            all_changes.append((snapshot, change))

    # First time we ever see this subscription: store a baseline silently.
    if is_baseline:
        subscription.last_state_snapshot = current_state
        subscription.last_polled_at = now
        subscription.last_poll_error = None
        subscription.poll_failure_count = 0
        await session.commit()
        return {"status": "baseline", "message": "Initial snapshot stored", "changes": 0}

    # Nothing meaningful changed this cycle: refresh the stored snapshot (so any
    # filtered-out blank edits are not re-detected later) and stop. No message.
    if not all_changes:
        subscription.last_state_snapshot = current_state
        subscription.last_polled_at = now
        subscription.last_poll_error = None
        subscription.poll_failure_count = 0
        await session.commit()
        return {"status": "ok", "changes": 0, "telegram_linked": user.telegram_chat_id is not None}

    telegram_linked = user.telegram_chat_id is not None
    sent_count = 0

    # Group changes by sheet, then send exactly ONE consolidated message for the
    # whole cycle (never split into multiple Telegram messages).
    groups: dict[str, tuple[Any, list[Any]]] = {}
    for snapshot, change in all_changes:
        entry = groups.get(snapshot.sheet_name)
        if entry is None:
            groups[snapshot.sheet_name] = (snapshot, [change])
        else:
            entry[1].append(change)

    message_sent = False
    if telegram_linked:
        message = format_changes_message(groups)
        message_sent = await send_telegram_message(user.telegram_chat_id, message)
        if message_sent:
            sent_count = 1

    # Persist one log row per change (full history) with a precise description.
    for snapshot, change in all_changes:
        description = describe_change(change)
        if not telegram_linked:
            status, error_message, sent_at = "skipped", "Telegram not linked", None
        elif message_sent:
            status, error_message, sent_at = "sent", None, now
        else:
            status, error_message, sent_at = "failed", "Failed to send Telegram message", None

        session.add(
            NotificationLog(
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
                detection_method=detection_method,
                telegram_message=description,
                status=status,
                error_message=error_message,
                sent_at=sent_at,
            )
        )

    subscription.last_state_snapshot = current_state
    subscription.last_polled_at = now
    subscription.last_poll_error = None
    subscription.poll_failure_count = 0
    await session.commit()

    return {
        "status": "ok",
        "changes": len(all_changes),
        "sent": sent_count,
        "telegram_linked": telegram_linked,
    }


async def process_webhook(session: AsyncSession, webhook_secret: str) -> dict[str, Any]:
    """Handle an Apps Script webhook hit.

    The payload from Apps Script is treated purely as a *trigger*: we look up the
    subscription by its secret and then run the exact same full-pull + snapshot
    diff as the poller, so updates/deletes anywhere in the sheet are detected
    (not just the last appended row). ``respect_interval`` is False because the
    webhook is an explicit real-time signal.
    """
    subscription = (
        await session.execute(
            select(SheetSubscription).where(
                SheetSubscription.webhook_secret == webhook_secret,
                SheetSubscription.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if subscription is None:
        return {"status": "error", "message": "Invalid or inactive webhook secret"}

    return await process_subscription_changes(
        session,
        subscription.id,
        detection_method="webhook",
        respect_interval=False,
        require_polling_enabled=False,
    )


async def process_drive_notification(
    session: AsyncSession,
    channel_id: str,
    channel_token: str | None,
) -> dict[str, Any]:
    """Handle a Google Drive push notification.

    The notification only tells us a *file* changed, so we run the full
    snapshot-diff for every active subscription on that spreadsheet. The channel
    token is validated to ensure the call really came from our registered watch.
    """
    from models.drive_channel import DriveWatchChannel  # local import avoids cycles

    channel = (
        await session.execute(
            select(DriveWatchChannel).where(DriveWatchChannel.channel_id == channel_id)
        )
    ).scalar_one_or_none()
    if channel is None:
        return {"status": "ignored", "message": "Unknown channel"}
    if channel_token is not None and channel_token != channel.channel_token:
        return {"status": "ignored", "message": "Invalid channel token"}

    subscription_ids = list(
        (
            await session.execute(
                select(SheetSubscription.id).where(
                    SheetSubscription.user_id == channel.user_id,
                    SheetSubscription.spreadsheet_id == channel.spreadsheet_id,
                    SheetSubscription.is_active.is_(True),
                )
            )
        ).scalars().all()
    )

    processed = 0
    for subscription_id in subscription_ids:
        await process_subscription_changes(
            session,
            subscription_id,
            detection_method="drive",
            respect_interval=False,
            require_polling_enabled=False,
        )
        processed += 1

    return {"status": "ok", "subscriptions_processed": processed}

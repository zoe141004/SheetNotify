"""
Notification service — process webhook data, render templates, send notifications.
"""

import html
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.subscription import SheetSubscription
from models.notification import NotificationLog
from services.telegram import send_telegram_message


def _escape_telegram_html(value: Any) -> str:
    return html.escape("") if value is None else html.escape(str(value))


def render_notification_template(
    template: Optional[str],
    row_data: dict[str, Any],
    spreadsheet_name: str,
    sheet_name: str,
    row_number: int,
) -> str:
    """
    Render a notification message from a template and row data.
    Template can use {{column_name}} placeholders.
    If no template provided, renders a default message.
    """
    if template:
        message = template
        for key, value in row_data.items():
            placeholder = "{{" + key + "}}"
            message = message.replace(placeholder, _escape_telegram_html(value))
        # Clean up any remaining placeholders
        message = re.sub(r"\{\{[^}]+\}\}", "", message)
        return message

    # Default template
    lines = [
        f"📊 <b>New data in {_escape_telegram_html(spreadsheet_name)}</b>",
        f"📋 Sheet: {_escape_telegram_html(sheet_name)} | Row #{row_number}",
        "─" * 25,
    ]
    for key, value in row_data.items():
        if value is not None and str(value).strip():
            lines.append(f"• <b>{_escape_telegram_html(key)}</b>: {_escape_telegram_html(value)}")
    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    return "\n".join(lines)


async def process_webhook_data(
    db: AsyncSession,
    webhook_secret: str,
    payload: dict[str, Any],
    source_ip: Optional[str] = None,
) -> dict[str, Any]:
    """
    Process incoming webhook data from Google Apps Script.
    Returns a result dict with status and message.
    """
    # Find subscription by webhook secret
    result = await db.execute(
        select(SheetSubscription).where(
            SheetSubscription.webhook_secret == webhook_secret,
            SheetSubscription.is_active == True,
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription is None:
        return {"status": "error", "message": "Invalid or inactive webhook secret"}

    from models.user import User
    user_result = await db.execute(
        select(User).where(User.id == subscription.user_id)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        return {"status": "error", "message": "User not found"}

    # Extract data from payload
    row_data = payload.get("row_data", {})
    row_number = payload.get("row_number", 0)
    spreadsheet_name = payload.get("spreadsheet_name", subscription.spreadsheet_name or "Unknown")
    sheet_name = payload.get("sheet_name", subscription.sheet_name)

    # Check if user has linked Telegram
    if not user.telegram_chat_id:
        # Log as skipped
        log = NotificationLog(
            user_id=user.id,
            subscription_id=subscription.id,
            spreadsheet_id=subscription.spreadsheet_id,
            spreadsheet_name=spreadsheet_name,
            sheet_name=sheet_name,
            row_number=row_number,
            row_data=row_data,
            status="skipped",
            error_message="Telegram not linked",
            source_ip=source_ip,
        )
        db.add(log)
        await db.flush()
        return {"status": "skipped", "message": "Telegram not linked"}

    # Render the notification message
    message = render_notification_template(
        template=subscription.notification_template,
        row_data=row_data,
        spreadsheet_name=spreadsheet_name,
        sheet_name=sheet_name,
        row_number=row_number,
    )

    # Send Telegram notification
    success = await send_telegram_message(user.telegram_chat_id, message)

    # Create log entry
    log = NotificationLog(
        user_id=user.id,
        subscription_id=subscription.id,
        spreadsheet_id=subscription.spreadsheet_id,
        spreadsheet_name=spreadsheet_name,
        sheet_name=sheet_name,
        row_number=row_number,
        row_data=row_data,
        telegram_message=message,
        status="sent" if success else "failed",
        error_message=None if success else "Failed to send Telegram message",
        sent_at=datetime.now(timezone.utc) if success else None,
        source_ip=source_ip,
    )
    db.add(log)

    # Update last known row
    if row_number and row_number > subscription.last_known_row:
        subscription.last_known_row = row_number
        subscription.updated_at = datetime.now(timezone.utc)

    await db.flush()

    return {
        "status": "sent" if success else "failed",
        "message": "Notification sent" if success else "Failed to send",
    }

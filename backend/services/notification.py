"""
Notification formatting — build the Telegram message for a detected change.

Message rendering is shared by every trigger (poller + webhook). The actual
detection and sending lives in :mod:`services.change_processor`.
"""

import html
from datetime import datetime, timezone
from typing import Any, Optional


def _escape_telegram_html(value: Any) -> str:
    return html.escape("") if value is None else html.escape(str(value))


def format_polling_notification(
    spreadsheet_name: str,
    sheet_name: str,
    change_type: str,
    row_number: int,
    changed_columns: list[str],
    before_data: Optional[dict[str, Any]] = None,
    after_data: Optional[dict[str, Any]] = None,
    cell_reference: Optional[str] = None,
) -> str:
    """Format a snapshot-diff notification with before/after context."""
    title_map = {
        "insert": "🟢 <b>New row inserted</b>",
        "update": "📝 <b>Row updated</b>",
        "delete": "🗑️ <b>Row deleted</b>",
    }
    lines = [
        title_map.get(change_type, "📊 <b>Sheet changed</b>"),
        f"📁 File: {_escape_telegram_html(spreadsheet_name)}",
        f"📄 Sheet: {_escape_telegram_html(sheet_name)}",
        f"📍 Row: #{row_number}",
    ]
    if cell_reference:
        lines.append(f"✏️ Cell: {_escape_telegram_html(cell_reference)}")
    if changed_columns and change_type == "update":
        lines.append(f"🧩 Changed columns: {_escape_telegram_html(', '.join(changed_columns))}")

    if before_data and after_data and change_type == "update":
        lines.append("\n<b>Before → After</b>")
        for column in changed_columns:
            before_value = before_data.get(column)
            after_value = after_data.get(column)
            lines.append(
                f"• <b>{_escape_telegram_html(column)}</b>: "
                f"{_escape_telegram_html(before_value)} → {_escape_telegram_html(after_value)}"
            )

    if after_data and change_type == "insert":
        lines.append("\n<b>Inserted values</b>")
        for key, value in after_data.items():
            if key == "_row_number":
                continue
            if value is not None and str(value).strip():
                lines.append(f"• <b>{_escape_telegram_html(key)}</b>: {_escape_telegram_html(value)}")

    if before_data and change_type == "delete":
        lines.append("\n<b>Deleted values</b>")
        for key, value in before_data.items():
            if key == "_row_number":
                continue
            if value is not None and str(value).strip():
                lines.append(f"• <b>{_escape_telegram_html(key)}</b>: {_escape_telegram_html(value)}")

    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    return "\n".join(lines)

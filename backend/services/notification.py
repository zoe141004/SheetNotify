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


def _non_blank_pairs(row: Optional[dict[str, Any]], limit: int = 3) -> str:
    """Compact 'k=v' summary of a row's non-blank cells (excluding row marker)."""
    if not row:
        return ""
    parts = []
    for key, value in row.items():
        if key == "_row_number":
            continue
        if value is not None and str(value).strip():
            parts.append(f"{_escape_telegram_html(key)}={_escape_telegram_html(value)}")
        if len(parts) >= limit:
            break
    return ", ".join(parts)


def _compact_change_line(change: Any) -> str:
    """One short line describing a single change, for batched summaries."""
    row_number = change.row_number
    if change.change_type == "insert":
        summary = _non_blank_pairs(change.after) or "(no content)"
        return f"🟢 #{row_number}: {summary}"
    if change.change_type == "delete":
        summary = _non_blank_pairs(change.before) or "(empty)"
        return f"🗑️ #{row_number}: {summary}"
    # update
    cols = change.changed_columns or []
    if len(cols) == 1 and change.before is not None and change.after is not None:
        col = cols[0]
        before = _escape_telegram_html(change.before.get(col))
        after = _escape_telegram_html(change.after.get(col))
        ref = change.cell_reference or f"#{row_number}"
        return f"📝 {_escape_telegram_html(ref)}: {before} → {after}"
    return f"📝 #{row_number}: {_escape_telegram_html(', '.join(cols))} updated"


def format_batched_notification(
    spreadsheet_name: str,
    sheet_name: str,
    changes: list[Any],
    max_detail: int = 8,
    max_chars: int = 3500,
) -> str:
    """Summarize many changes from one detection cycle into a single message."""
    inserts = sum(1 for c in changes if c.change_type == "insert")
    updates = sum(1 for c in changes if c.change_type == "update")
    deletes = sum(1 for c in changes if c.change_type == "delete")

    lines = [
        f"📊 <b>{len(changes)} changes</b> in {_escape_telegram_html(spreadsheet_name)} / {_escape_telegram_html(sheet_name)}",
    ]
    summary_bits = []
    if inserts:
        summary_bits.append(f"🟢 {inserts} added")
    if updates:
        summary_bits.append(f"📝 {updates} updated")
    if deletes:
        summary_bits.append(f"🗑️ {deletes} deleted")
    if summary_bits:
        lines.append(" · ".join(summary_bits))

    lines.append("")
    shown = 0
    for change in changes:
        if shown >= max_detail:
            break
        line = _compact_change_line(change)
        # Stop early if we are about to overflow Telegram's message limit.
        if sum(len(x) for x in lines) + len(line) > max_chars:
            break
        lines.append(line)
        shown += 1

    remaining = len(changes) - shown
    if remaining > 0:
        lines.append(f"… and {remaining} more change(s)")

    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    return "\n".join(lines)

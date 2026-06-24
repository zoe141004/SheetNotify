"""
Notification formatting — turn detected changes into Telegram messages.

Every detection cycle produces exactly ONE Telegram message (never split), via
``format_changes_message``. Each change is described accurately:
  * inserts  → counted, with row-number ranges (e.g. "Added 1000 rows (#3–#1002)")
  * updates  → A1 cell reference + what happened
               ("A3: added \"abc\"" / "E2: \"present\" → \"absent\"")
  * deletes  → counted, with row-number ranges ("Deleted row #15")

``describe_change`` returns the single-line description and is reused for the
per-change database log entries.
"""

import html
from datetime import datetime, timezone
from typing import Any, Optional


def _escape(value: Any) -> str:
    return html.escape("") if value is None else html.escape(str(value))


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _non_blank_pairs(row: Optional[dict[str, Any]], limit: int = 4) -> str:
    """Compact 'k=v' summary of a row's non-blank cells (excluding row marker)."""
    if not row:
        return ""
    parts = []
    for key, value in row.items():
        if key == "_row_number" or _is_blank(value):
            continue
        parts.append(f"{_escape(key)}={_escape(value)}")
        if len(parts) >= limit:
            break
    return ", ".join(parts)


def _compress_ranges(numbers: list[int]) -> str:
    """[3,4,5,8] → '#3–#5, #8' for compact row-range display."""
    unique = sorted(set(numbers))
    if not unique:
        return ""
    spans: list[tuple[int, int]] = []
    start = prev = unique[0]
    for n in unique[1:]:
        if n == prev + 1:
            prev = n
            continue
        spans.append((start, prev))
        start = prev = n
    spans.append((start, prev))
    return ", ".join(f"#{a}" if a == b else f"#{a}–#{b}" for a, b in spans)


def describe_change(change: Any) -> str:
    """One precise, human-readable line describing a single change."""
    row_number = change.row_number

    if change.change_type == "insert":
        content = _non_blank_pairs(change.after)
        return f"➕ Row #{row_number}" + (f": {content}" if content else "")

    if change.change_type == "delete":
        content = _non_blank_pairs(change.before)
        return f"🗑️ Deleted row #{row_number}" + (f" ({content})" if content else "")

    # update
    cols = change.changed_columns or []
    if len(cols) == 1:
        col = cols[0]
        before = change.before.get(col) if change.before else None
        after = change.after.get(col) if change.after else None
        ref = change.cell_reference or f"#{row_number}"
        label = f"{_escape(ref)} ({_escape(col)})"
        if _is_blank(before) and not _is_blank(after):
            return f'✏️ {label}: added "{_escape(after)}"'
        if _is_blank(after) and not _is_blank(before):
            return f'✏️ {label}: cleared (was "{_escape(before)}")'
        return f'✏️ {label}: "{_escape(before)}" → "{_escape(after)}"'

    return f"✏️ Row #{row_number}: updated {_escape(', '.join(cols))}"


def _sheet_section(changes: list[Any], max_update_lines: int) -> list[str]:
    inserts = [c for c in changes if c.change_type == "insert"]
    updates = [c for c in changes if c.change_type == "update"]
    deletes = [c for c in changes if c.change_type == "delete"]

    lines: list[str] = []

    if inserts:
        if len(inserts) <= 5:
            lines.extend(describe_change(c) for c in inserts)
        else:
            rng = _compress_ranges([c.row_number for c in inserts])
            lines.append(f"➕ Added {len(inserts)} rows ({rng})")

    shown = 0
    for change in updates:
        if shown >= max_update_lines:
            break
        lines.append(describe_change(change))
        shown += 1
    if len(updates) > shown:
        lines.append(f"✏️ … +{len(updates) - shown} more update(s)")

    if deletes:
        if len(deletes) <= 5:
            lines.extend(describe_change(c) for c in deletes)
        else:
            rng = _compress_ranges([c.row_number for c in deletes])
            lines.append(f"🗑️ Deleted {len(deletes)} rows ({rng})")

    return lines


def format_changes_message(
    groups: dict[str, tuple[Any, list[Any]]],
    max_update_lines: int = 25,
    max_chars: int = 3800,
) -> str:
    """Build a SINGLE Telegram message describing all changes in one cycle.

    ``groups`` maps sheet name → (snapshot, changes). Changes from every sheet
    are combined into one message (Telegram allows ~4096 chars; we cap and add
    a truncation note if needed).
    """
    total = sum(len(changes) for _, changes in groups.values())
    multi_sheet = len(groups) > 1

    first_snapshot = next(iter(groups.values()))[0]
    spreadsheet_name = first_snapshot.spreadsheet_name

    if multi_sheet:
        header = f"🔔 <b>{_escape(spreadsheet_name)}</b> — {total} change(s)"
    else:
        sheet_name = next(iter(groups.keys()))
        header = f"🔔 <b>{_escape(spreadsheet_name)} / {_escape(sheet_name)}</b> — {total} change(s)"

    body: list[str] = []
    truncated = False
    for sheet_name, (_snapshot, changes) in groups.items():
        section = _sheet_section(changes, max_update_lines)
        if multi_sheet:
            section = [f"\n📄 <b>{_escape(sheet_name)}</b>", *section]
        for line in section:
            if len(header) + sum(len(x) + 1 for x in body) + len(line) > max_chars:
                truncated = True
                break
            body.append(line)
        if truncated:
            break

    if truncated:
        body.append("… (message truncated)")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([header, "", *body, f"\n🕐 {timestamp}"])

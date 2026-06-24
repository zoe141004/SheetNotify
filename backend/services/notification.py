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
import re
from datetime import datetime, timezone
from typing import Any, Optional

from services.change_detector import column_index


def _escape(value: Any) -> str:
    return html.escape("") if value is None else html.escape(str(value))


_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _ref_parts(ref: str) -> tuple[str, int] | None:
    match = _REF_RE.match(ref or "")
    if not match:
        return None
    return match.group(1), int(match.group(2))


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


def _describe_cell(ref: str, col_name: str, before: Any, after: Any) -> str:
    label = f"{_escape(ref)} ({_escape(col_name)})"
    if _is_blank(before) and not _is_blank(after):
        return f'✏️ {label}: added "{_escape(after)}"'
    if _is_blank(after) and not _is_blank(before):
        return f'✏️ {label}: cleared (was "{_escape(before)}")'
    return f'✏️ {label}: "{_escape(before)}" → "{_escape(after)}"'


def describe_change(change: Any) -> str:
    """One precise, human-readable line describing a single change.

    Reused for per-change DB log entries (the consolidated Telegram message is
    built separately by format_changes_message).
    """
    row_number = change.row_number
    cols = change.changed_columns or []

    if change.change_type == "column_insert":
        return f"➕ Added column {_escape(change.cell_reference)} ({_escape(cols[0] if cols else '')})"
    if change.change_type == "column_delete":
        return f"🗑️ Deleted column {_escape(change.cell_reference)} ({_escape(cols[0] if cols else '')})"

    if change.change_type == "insert":
        content = _non_blank_pairs(change.after)
        return f"➕ Row #{row_number}" + (f": {content}" if content else "")

    if change.change_type == "delete":
        content = _non_blank_pairs(change.before)
        return f"🗑️ Deleted row #{row_number}" + (f" ({content})" if content else "")

    # update
    if len(cols) == 1:
        col = cols[0]
        before = change.before.get(col) if change.before else None
        after = change.after.get(col) if change.after else None
        ref = change.cell_reference or f"#{row_number}"
        return _describe_cell(ref, col, before, after)

    return f"✏️ Row #{row_number}: updated {_escape(', '.join(cols))}"


def _summarize_updates(updates: list[Any], max_lines: int) -> list[str]:
    """Group changed cells into per-cell / range / column / rectangle summaries."""
    # Flatten every changed cell across all update rows.
    cells: list[tuple[int, int, str, Any, Any, str]] = []  # (col_idx,row,col,before,after,ref)
    for change in updates:
        before = change.before or {}
        after = change.after or {}
        for col, ref in zip(change.changed_columns, change.changed_cell_refs):
            parts = _ref_parts(ref)
            col_idx = column_index(parts[0]) if parts else 0
            cells.append((col_idx, change.row_number, col, before.get(col), after.get(col), ref))

    if not cells:
        return []

    # Few cells → show each precisely (with before → after).
    if len(cells) <= 6:
        return [_describe_cell(ref, col, before, after) for _, _, col, before, after, ref in cells]

    rows = sorted({c[1] for c in cells})
    col_idxs = sorted({c[0] for c in cells})
    contiguous_rows = rows == list(range(rows[0], rows[-1] + 1))
    contiguous_cols = col_idxs == list(range(col_idxs[0], col_idxs[-1] + 1))

    from services.change_detector import column_letter

    # Perfect rectangle (every cell in the block changed) → single range.
    if (
        len(col_idxs) > 1
        and contiguous_rows
        and contiguous_cols
        and len(cells) == len(rows) * len(col_idxs)
    ):
        top_left = f"{column_letter(col_idxs[0])}{rows[0]}"
        bottom_right = f"{column_letter(col_idxs[-1])}{rows[-1]}"
        return [f"✏️ {top_left}:{bottom_right} updated ({len(cells)} cells)"]

    # Otherwise summarize per column.
    lines: list[str] = []
    by_col: dict[int, list[tuple[int, str, str]]] = {}
    for col_idx, row, col, _b, _a, ref in cells:
        by_col.setdefault(col_idx, []).append((row, col, ref))
    for col_idx in sorted(by_col):
        entries = sorted(by_col[col_idx])
        col_rows = [e[0] for e in entries]
        col_name = entries[0][1]
        letter = column_letter(col_idx)
        if len(entries) == 1:
            row = col_rows[0]
            change = next(u for u in updates if u.row_number == row)
            lines.append(_describe_cell(f"{letter}{row}", col_name, (change.before or {}).get(col_name), (change.after or {}).get(col_name)))
        elif col_rows == list(range(col_rows[0], col_rows[-1] + 1)):
            lines.append(
                f"✏️ {letter}{col_rows[0]}:{letter}{col_rows[-1]} ({_escape(col_name)}): {len(entries)} cells updated"
            )
        else:
            lines.append(
                f"✏️ Column {letter} ({_escape(col_name)}): {len(entries)} cells updated ({_compress_ranges(col_rows)})"
            )
        if len(lines) >= max_lines:
            remaining_cols = len(by_col) - len(lines)
            if remaining_cols > 0:
                lines.append(f"✏️ … +{remaining_cols} more column(s) changed")
            break
    return lines


def _sheet_section(changes: list[Any], max_update_lines: int) -> list[str]:
    col_inserts = [c for c in changes if c.change_type == "column_insert"]
    col_deletes = [c for c in changes if c.change_type == "column_delete"]
    inserts = [c for c in changes if c.change_type == "insert"]
    updates = [c for c in changes if c.change_type == "update"]
    deletes = [c for c in changes if c.change_type == "delete"]

    lines: list[str] = []

    # Column-level events first.
    lines.extend(describe_change(c) for c in col_inserts)
    lines.extend(describe_change(c) for c in col_deletes)

    # Row inserts.
    if inserts:
        if len(inserts) <= 5:
            lines.extend(describe_change(c) for c in inserts)
        else:
            rng = _compress_ranges([c.row_number for c in inserts])
            lines.append(f"➕ Added {len(inserts)} rows ({rng})")

    # Cell updates (grouped into cells / ranges / columns / rectangles).
    lines.extend(_summarize_updates(updates, max_update_lines))

    # Row deletes.
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
    if not groups:
        return ""

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

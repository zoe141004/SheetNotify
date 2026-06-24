"""
Change detection helpers for snapshot-based sheet monitoring.

The detector compares two snapshots of a sheet (the previously stored snapshot
and the freshly fetched one) and classifies every difference as an insert,
update, or delete. Matching is content-based (via a stable per-row hash) so that
inserting or deleting a row in the *middle* of a sheet does not cascade into a
flood of false "update" notifications — the rows that merely shifted position
are recognised as unchanged because their content hash still matches.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CellChange:
    column: str
    before: Any
    after: Any


@dataclass(slots=True)
class RowChange:
    change_type: str
    row_number: int
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    changed_columns: list[str]
    cell_reference: str | None = None


def _normalize(value: Any) -> str:
    """Collapse blank-ish values so they compare equal.

    None, "", and whitespace-only all become "" — so a cell going from null to
    an empty string (or vice versa) is NOT treated as a change. Other values are
    trimmed of surrounding whitespace.
    """
    if value is None:
        return ""
    return str(value).strip()


def _stable_row_hash(row: dict[str, Any], headers: list[str]) -> str:
    """Hash a row's *normalized* content (ignoring position and blank/whitespace noise)."""
    payload = {header: _normalize(row.get(header)) for header in headers}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _row_is_empty(row: dict[str, Any] | None, headers: list[str]) -> bool:
    """True if every tracked cell of the row is blank/whitespace."""
    if not row:
        return True
    return all(_normalize(row.get(header)) == "" for header in headers)


def column_letter(index: int) -> str:
    """0-based column index → spreadsheet letter (0→A, 25→Z, 26→AA)."""
    result = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _row_number_of(row: dict[str, Any], fallback: int) -> int:
    try:
        return int(row.get("_row_number", fallback))
    except (TypeError, ValueError):
        return fallback


def detect_changes(
    previous_rows: list[dict[str, Any]] | None,
    current_rows: list[dict[str, Any]],
    headers: list[str],
) -> list[RowChange]:
    """Detect row-level inserts, updates, and deletions between two snapshots.

    Algorithm:
      1. Match rows whose *content* is identical (same hash). These are treated
         as unchanged even if their row number moved (e.g. a row was inserted
         above them). When several rows share the same hash we pair them up by
         closest row number to stay stable.
      2. Remaining current rows that share a row number with a remaining
         previous row → UPDATE (compute exactly which columns changed).
      3. Remaining current rows with no previous counterpart → INSERT.
      4. Remaining previous rows with no current counterpart → DELETE.
    """
    previous_rows = previous_rows or []

    prev = [
        (_row_number_of(row, index + 2), row, _stable_row_hash(row, headers))
        for index, row in enumerate(previous_rows)
    ]
    curr = [
        (_row_number_of(row, index + 2), row, _stable_row_hash(row, headers))
        for index, row in enumerate(current_rows)
    ]

    # ── Step 1: match identical-content rows ──
    prev_by_hash: dict[str, list[int]] = defaultdict(list)
    for index, (_, _, row_hash) in enumerate(prev):
        prev_by_hash[row_hash].append(index)

    prev_matched: set[int] = set()
    curr_matched: set[int] = set()

    for curr_index, (curr_number, _, curr_hash) in enumerate(curr):
        candidates = prev_by_hash.get(curr_hash)
        if not candidates:
            continue
        best_index: int | None = None
        for prev_index in candidates:
            if prev_index in prev_matched:
                continue
            if best_index is None or abs(prev[prev_index][0] - curr_number) < abs(
                prev[best_index][0] - curr_number
            ):
                best_index = prev_index
        if best_index is not None:
            prev_matched.add(best_index)
            curr_matched.add(curr_index)

    remaining_prev = [prev[i] for i in range(len(prev)) if i not in prev_matched]
    remaining_curr = [curr[i] for i in range(len(curr)) if i not in curr_matched]

    # ── Steps 2 & 3: updates and inserts ──
    remaining_prev_by_number: dict[int, tuple[int, dict[str, Any], str]] = {
        item[0]: item for item in remaining_prev
    }
    consumed_prev_numbers: set[int] = set()
    changes: list[RowChange] = []

    for curr_number, curr_row, _ in remaining_curr:
        prev_item = remaining_prev_by_number.get(curr_number)
        if prev_item is not None and curr_number not in consumed_prev_numbers:
            _, prev_row, _ = prev_item
            consumed_prev_numbers.add(curr_number)
            # Compare normalized values so null<->"" / whitespace edits are ignored.
            changed_columns = [
                header
                for header in headers
                if _normalize(prev_row.get(header)) != _normalize(curr_row.get(header))
            ]
            if changed_columns:
                # Single-cell edits get an A1-style reference (e.g. "E2"); the
                # column letter comes from the header's position in the sheet.
                if len(changed_columns) == 1:
                    col_index = headers.index(changed_columns[0])
                    cell_reference = f"{column_letter(col_index)}{curr_number}"
                else:
                    cell_reference = None
                changes.append(
                    RowChange(
                        change_type="update",
                        row_number=curr_number,
                        before=prev_row,
                        after=curr_row,
                        changed_columns=changed_columns,
                        cell_reference=cell_reference,
                    )
                )
        else:
            # Skip brand-new rows that carry no actual content (blank rows added
            # when extending a table, etc.) — nothing meaningful to report.
            if _row_is_empty(curr_row, headers):
                continue
            changes.append(
                RowChange(
                    change_type="insert",
                    row_number=curr_number,
                    before=None,
                    after=curr_row,
                    changed_columns=list(headers),
                )
            )

    # ── Step 4: deletes ──
    for prev_number, prev_row, _ in remaining_prev:
        if prev_number in consumed_prev_numbers:
            continue
        # Don't announce the removal of a row that never had content.
        if _row_is_empty(prev_row, headers):
            continue
        changes.append(
            RowChange(
                change_type="delete",
                row_number=prev_number,
                before=prev_row,
                after=None,
                changed_columns=list(headers),
            )
        )

    changes.sort(key=lambda change: change.row_number)
    return changes


def snapshot_rows(rows: list[dict[str, Any]], headers: list[str]) -> dict[str, Any]:
    """Build the persisted snapshot payload for a single sheet."""
    return {
        "headers": headers,
        "rows": rows,
        "row_hashes": [_stable_row_hash(row, headers) for row in rows],
    }

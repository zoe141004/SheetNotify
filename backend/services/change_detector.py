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
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CellChange:
    column: str
    before: Any
    after: Any


@dataclass(slots=True)
class RowChange:
    # change_type: "insert" | "update" | "delete" (row-level)
    #            | "column_insert" | "column_delete" (column-level)
    change_type: str
    row_number: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    changed_columns: list[str]
    cell_reference: str | None = None
    # A1 references of every changed cell in this row (e.g. ["B7", "D7"]),
    # used by the formatter to group cells into ranges/rectangles/columns.
    changed_cell_refs: list[str] = field(default_factory=list)


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


def column_index(letter: str) -> int:
    """Spreadsheet letter → 0-based column index ('A'→0, 'Z'→25, 'AA'→26)."""
    value = 0
    for char in letter:
        value = value * 26 + (ord(char) - 64)
    return value - 1


def _row_number_of(row: dict[str, Any], fallback: int) -> int:
    try:
        return int(row.get("_row_number", fallback))
    except (TypeError, ValueError):
        return fallback


def detect_changes(
    previous_rows: list[dict[str, Any]] | None,
    current_rows: list[dict[str, Any]],
    headers: list[str],
    previous_headers: list[str] | None = None,
) -> list[RowChange]:
    """Detect cell-, column-, and row-level changes between two snapshots.

    Granularity covered:
      * COLUMN insert/delete — a header present on one side only. Reported once
        ("Added column E") instead of as an update on every row.
      * ROW insert/delete — a whole row added/removed (content-matched so a
        mid-sheet insert doesn't cascade into false updates).
      * CELL update — a cell whose value changed. Each carries its A1 reference
        (e.g. "E2") so the formatter can group cells into ranges/columns.

    Only columns present in BOTH snapshots are diffed for row/cell changes, so a
    column add/remove is attributed to the column event, not to every row.
    """
    previous_rows = previous_rows or []
    if previous_headers is None:
        previous_headers = headers  # unknown previous schema → assume unchanged

    prev_header_set = set(previous_headers)
    curr_header_set = set(headers)
    common_headers = [h for h in headers if h in prev_header_set]
    col_index_of = {h: headers.index(h) for h in headers}

    changes: list[RowChange] = []

    # ── Column-level changes (header set diff) ──
    if previous_headers:
        for header in headers:
            if header not in prev_header_set:
                changes.append(
                    RowChange(
                        change_type="column_insert",
                        row_number=None,
                        before=None,
                        after=None,
                        changed_columns=[header],
                        cell_reference=column_letter(headers.index(header)),
                    )
                )
        for header in previous_headers:
            if header not in curr_header_set:
                changes.append(
                    RowChange(
                        change_type="column_delete",
                        row_number=None,
                        before=None,
                        after=None,
                        changed_columns=[header],
                        cell_reference=column_letter(previous_headers.index(header)),
                    )
                )

    # ── Row matching on common-column content ──
    prev = [
        (_row_number_of(row, index + 2), row, _stable_row_hash(row, common_headers))
        for index, row in enumerate(previous_rows)
    ]
    curr = [
        (_row_number_of(row, index + 2), row, _stable_row_hash(row, common_headers))
        for index, row in enumerate(current_rows)
    ]

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

    # ── Updates and inserts ──
    remaining_prev_by_number: dict[int, tuple[int, dict[str, Any], str]] = {
        item[0]: item for item in remaining_prev
    }
    consumed_prev_numbers: set[int] = set()

    for curr_number, curr_row, _ in remaining_curr:
        prev_item = remaining_prev_by_number.get(curr_number)
        if prev_item is not None and curr_number not in consumed_prev_numbers:
            _, prev_row, _ = prev_item
            consumed_prev_numbers.add(curr_number)
            # Compare normalized values over COMMON columns only.
            changed_columns = [
                header
                for header in common_headers
                if _normalize(prev_row.get(header)) != _normalize(curr_row.get(header))
            ]
            if changed_columns:
                changed_cell_refs = [
                    f"{column_letter(col_index_of[col])}{curr_number}"
                    for col in changed_columns
                ]
                cell_reference = changed_cell_refs[0] if len(changed_columns) == 1 else None
                changes.append(
                    RowChange(
                        change_type="update",
                        row_number=curr_number,
                        before=prev_row,
                        after=curr_row,
                        changed_columns=changed_columns,
                        cell_reference=cell_reference,
                        changed_cell_refs=changed_cell_refs,
                    )
                )
        else:
            # Skip brand-new rows with no content (blank rows added when
            # extending a table, etc.).
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

    # ── Deletes ──
    for prev_number, prev_row, _ in remaining_prev:
        if prev_number in consumed_prev_numbers:
            continue
        if _row_is_empty(prev_row, previous_headers):
            continue
        changes.append(
            RowChange(
                change_type="delete",
                row_number=prev_number,
                before=prev_row,
                after=None,
                changed_columns=list(previous_headers),
            )
        )

    changes.sort(key=lambda change: (change.row_number if change.row_number is not None else -1))
    return changes


def snapshot_rows(rows: list[dict[str, Any]], headers: list[str]) -> dict[str, Any]:
    """Build the persisted snapshot payload for a single sheet."""
    return {
        "headers": headers,
        "rows": rows,
        "row_hashes": [_stable_row_hash(row, headers) for row in rows],
    }

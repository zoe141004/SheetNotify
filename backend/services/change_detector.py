"""
Change detection helpers for polling-based sheet monitoring.
"""

from __future__ import annotations

import hashlib
import json
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


def _stable_row_hash(row: dict[str, Any], headers: list[str]) -> str:
    payload = {header: row.get(header) for header in headers}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def detect_changes(
    previous_rows: list[dict[str, Any]] | None,
    current_rows: list[dict[str, Any]],
    headers: list[str],
) -> list[RowChange]:
    """Detect row-level inserts, updates, and deletions between two snapshots."""
    previous_rows = previous_rows or []
    previous_by_key: dict[int, dict[str, Any]] = {
        int(row.get("_row_number", index + 2)): row
        for index, row in enumerate(previous_rows)
    }
    current_by_key: dict[int, dict[str, Any]] = {
        int(row.get("_row_number", index + 2)): row
        for index, row in enumerate(current_rows)
    }

    changes: list[RowChange] = []
    all_row_numbers = sorted(set(previous_by_key) | set(current_by_key))

    for row_number in all_row_numbers:
        before_row = previous_by_key.get(row_number)
        after_row = current_by_key.get(row_number)

        if before_row is None and after_row is not None:
            changes.append(
                RowChange(
                    change_type="insert",
                    row_number=row_number,
                    before=None,
                    after=after_row,
                    changed_columns=headers,
                )
            )
            continue

        if before_row is not None and after_row is None:
            changes.append(
                RowChange(
                    change_type="delete",
                    row_number=row_number,
                    before=before_row,
                    after=None,
                    changed_columns=headers,
                )
            )
            continue

        if before_row is None or after_row is None:
            continue

        changed_columns: list[str] = []
        for header in headers:
            if before_row.get(header) != after_row.get(header):
                changed_columns.append(header)

        if changed_columns:
            cell_reference = f"{changed_columns[0]}{row_number}" if len(changed_columns) == 1 else None
            changes.append(
                RowChange(
                    change_type="update",
                    row_number=row_number,
                    before=before_row,
                    after=after_row,
                    changed_columns=changed_columns,
                    cell_reference=cell_reference,
                )
            )

    return changes


def snapshot_rows(rows: list[dict[str, Any]], headers: list[str]) -> dict[str, Any]:
    return {
        "headers": headers,
        "rows": rows,
        "row_hashes": [
            _stable_row_hash(row, headers)
            for row in rows
        ],
    }
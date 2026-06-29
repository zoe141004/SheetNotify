"""Tests for single-message notification formatting."""

from services.change_detector import detect_changes
from services.notification import format_changes_message, describe_change

HEADERS = ["Name", "Age", "City"]


class _Snap:
    spreadsheet_name = "Sales"
    sheet_name = "Sheet1"


def row(n, *values):
    data = {"_row_number": n}
    for i, header in enumerate(HEADERS):
        data[header] = values[i] if i < len(values) else ""
    return data


def message(prev, curr, headers=HEADERS, prev_headers=HEADERS):
    changes = detect_changes(prev, curr, headers, prev_headers)
    return format_changes_message({"Sheet1": (_Snap(), changes)})


def test_empty_groups_returns_empty_string():
    assert format_changes_message({}) == ""


def test_single_cell_message():
    msg = message([row(2, "Mary", "30")], [row(2, "Mary", "31")])
    assert "B2 (Age)" in msg
    assert '"30" → "31"' in msg
    # exactly one header line, one change
    assert msg.count("🔔") == 1


def test_bulk_insert_is_one_message_with_range():
    prev = [row(2, "Seed", "1", "x")]
    curr = prev + [row(i, f"U{i}", "1", "y") for i in range(3, 1003)]
    msg = message(prev, curr)
    assert "Added 1000 rows" in msg
    assert "#3" in msg and "#1002" in msg
    # one consolidated message (single header, well under Telegram's limit)
    assert msg.count("🔔") == 1
    assert len(msg) < 4096


def test_column_range_grouped():
    prev = [row(i, f"N{i}", "20", "") for i in range(2, 10)]
    curr = [row(i, f"N{i}", "20", f"C{i}") for i in range(2, 10)]
    msg = message(prev, curr)
    assert "C2:C9" in msg
    assert "8 cells updated" in msg


def test_rectangle_grouped():
    prev = [row(i, "x", "y", "z") for i in range(2, 5)]
    curr = [row(i, "X", "Y", "Z") for i in range(2, 5)]
    msg = message(prev, curr)
    assert "A2:C4" in msg
    assert "9 cells" in msg


def test_describe_change_added_vs_changed():
    # added content (blank -> value)
    fill = detect_changes([row(2, "", "30")], [row(2, "abc", "30")], HEADERS, HEADERS)[0]
    assert 'added "abc"' in describe_change(fill)
    # value -> value
    edit = detect_changes([row(2, "Mary", "30")], [row(2, "Mary", "31")], HEADERS, HEADERS)[0]
    assert '"30" → "31"' in describe_change(edit)

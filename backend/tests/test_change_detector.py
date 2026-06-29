"""Unit tests for the snapshot diff engine (cell / range / column / row)."""

from services.change_detector import detect_changes, column_letter, column_index

HEADERS = ["Name", "Age", "City"]


def row(n, *values):
    data = {"_row_number": n}
    for i, header in enumerate(HEADERS):
        data[header] = values[i] if i < len(values) else ""
    return data


def types(changes):
    return [(c.change_type, c.row_number) for c in changes]


# ── column letter helpers ──

def test_column_letter_roundtrip():
    for i in (0, 1, 25, 26, 27, 51, 52, 701, 702):
        assert column_index(column_letter(i)) == i


# ── noise filtering ──

def test_null_to_empty_is_not_a_change():
    assert detect_changes([row(2, None, None, None)], [row(2, "", "", "")], HEADERS, HEADERS) == []


def test_whitespace_only_edit_ignored():
    assert detect_changes([row(2, "John")], [row(2, "John ")], HEADERS, HEADERS) == []


def test_blank_rows_added_are_ignored():
    prev = [row(2, "John", "30", "NY")]
    curr = [row(2, "John", "30", "NY"), row(3, "", "", ""), row(4, None, None, None)]
    assert detect_changes(prev, curr, HEADERS, HEADERS) == []


# ── row-level ──

def test_append_new_row():
    prev = [row(2, "A")]
    curr = [row(2, "A"), row(3, "B")]
    assert types(detect_changes(prev, curr, HEADERS, HEADERS)) == [("insert", 3)]


def test_mid_insert_is_single_insert_not_cascade():
    prev = [row(2, "A"), row(3, "B"), row(4, "C")]
    curr = [row(2, "A"), row(3, "NEW"), row(4, "B"), row(5, "C")]
    result = detect_changes(prev, curr, HEADERS, HEADERS)
    assert types(result) == [("insert", 3)]


def test_mid_delete_is_single_delete():
    prev = [row(2, "A"), row(3, "B"), row(4, "C")]
    curr = [row(2, "A"), row(3, "C")]
    assert types(detect_changes(prev, curr, HEADERS, HEADERS)) == [("delete", 3)]


def test_delete_blank_row_ignored():
    prev = [row(2, "A"), row(3, "", "", "")]
    curr = [row(2, "A")]
    assert detect_changes(prev, curr, HEADERS, HEADERS) == []


# ── cell-level ──

def test_single_cell_update_has_a1_reference():
    prev = [row(2, "Mary", "30", "NY")]
    curr = [row(2, "Mary", "31", "NY")]
    result = detect_changes(prev, curr, HEADERS, HEADERS)
    assert len(result) == 1
    change = result[0]
    assert change.change_type == "update"
    assert change.changed_columns == ["Age"]
    assert change.cell_reference == "B2"  # Age is column B, row 2


def test_fill_empty_cell_is_update():
    prev = [row(2, "", "30", "NY")]
    curr = [row(2, "abc", "30", "NY")]
    result = detect_changes(prev, curr, HEADERS, HEADERS)
    assert result[0].change_type == "update"
    assert result[0].cell_reference == "A2"


# ── column-level ──

def test_add_column_reported_once_not_per_row():
    prev_headers = ["Name", "Age", "City"]
    headers = ["Name", "Age", "City", "Status"]

    def r4(n, *v):
        d = {"_row_number": n}
        for i, h in enumerate(headers):
            d[h] = v[i] if i < len(v) else ""
        return d

    prev = [row(2, "Mary", "30", "NY"), row(3, "Bob", "40", "LA")]
    curr = [r4(2, "Mary", "30", "NY", "present"), r4(3, "Bob", "40", "LA", "absent")]
    result = detect_changes(prev, curr, headers, prev_headers)
    assert types(result) == [("column_insert", None)]
    assert result[0].cell_reference == "D"


def test_delete_column():
    prev_headers = ["Name", "Age", "City"]
    headers = ["Name", "Age"]

    def r2(n, *v):
        d = {"_row_number": n}
        for i, h in enumerate(headers):
            d[h] = v[i] if i < len(v) else ""
        return d

    prev = [row(2, "Mary", "30", "NY")]
    curr = [r2(2, "Mary", "30")]
    result = detect_changes(prev, curr, headers, prev_headers)
    assert types(result) == [("column_delete", None)]
    assert result[0].cell_reference == "C"


# ── baseline ──

def test_baseline_unknown_previous_headers_no_column_events():
    # previous_headers=None → treat schema as unchanged (no column add/del noise)
    curr = [row(2, "A"), row(3, "B")]
    result = detect_changes(None, curr, HEADERS, None)
    assert all(c.change_type == "insert" for c in result)
    assert {c.row_number for c in result} == {2, 3}

"""
No mocks here — this exercises the real pandas parsing path, since it
needs neither Postgres nor Groq. extract_json_from_excel() tries
pd.read_excel() first and falls back to pd.read_csv() on failure, so a
plain CSV path exercises both branches.
"""

import csv

from app.utils.excel_parser import extract_json_from_excel


def test_extract_json_from_excel_parses_csv(tmp_path):
    csv_path = tmp_path / "people.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "age"])
        writer.writerow(["Alice", "30"])
        writer.writerow(["Bob", "25"])

    result = extract_json_from_excel(str(csv_path))

    assert result["columns"] == ["name", "age"]
    assert result["schema"] == {"name": "string", "age": "string"}
    # pandas infers "age" as an int column since every value parses cleanly
    assert result["data"] == [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]
    assert result["rows"] == result["data"]


def test_extract_json_from_excel_fills_missing_values(tmp_path):
    csv_path = tmp_path / "partial.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "notes"])
        writer.writerow(["Alice", ""])
        writer.writerow(["Bob", "vip"])

    result = extract_json_from_excel(str(csv_path))

    # NaN/empty cells are filled with "" rather than left as null
    assert result["data"][0]["notes"] == ""
    assert result["data"][1]["notes"] == "vip"

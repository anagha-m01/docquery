"""
excel_parser.py
───────────────
Reads .xlsx/.xls/.csv into the {schema, data, rows, columns} shape the
rest of the app expects, tries pd.read_excel then falls back to
pd.read_csv (so a .csv-with-.xlsx-extension still parses).

Empty and corrupt files are turned into clear ValueErrors rather than a
raw pandas/openpyxl traceback.
"""

import pandas as pd


def extract_json_from_excel(file_path: str) -> dict:
    try:
        df = pd.read_excel(file_path)
    except Exception:
        try:
            df = pd.read_csv(file_path)
        except pd.errors.EmptyDataError:
            raise ValueError("This file is empty — there's no data to extract.")
        except Exception as e:
            raise ValueError(
                "This file could not be read — it may be corrupted or in an unsupported format."
            ) from e

    if df.shape[1] == 0:
        raise ValueError("This file is empty — there's no data to extract.")

    if df.shape[0] == 0:
        # Headers but no rows — valid, just nothing to embed/search later.
        columns = list(df.columns)
        return {
            "schema": {col: "string" for col in columns},
            "data": [],
            "rows": [],
            "columns": columns,
        }

    columns = list(df.columns)

    # Schema: actual column names as keys — editable in UI
    schema = {col: "string" for col in columns}

    rows = df.fillna("").to_dict(orient="records")

    return {
        "schema": schema,
        "data": rows,
        "rows": rows,       # explicit reference used by embeddings pipeline
        "columns": columns,
    }

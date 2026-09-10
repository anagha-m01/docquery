import pandas as pd

def extract_json_from_excel(file_path: str) -> dict:
    try:
        df = pd.read_excel(file_path)
    except Exception:
        df = pd.read_csv(file_path)

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
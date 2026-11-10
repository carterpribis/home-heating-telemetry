"""Load the logger's Google Sheet export and clean it.

Input: the sheet downloaded as an Excel file (File > Download > Microsoft Excel).
The logger writes one tab per ISO week, named oil_usage_YYYY_WW. This module
joins those tabs into one table and marks which stove readings can be trusted.
"""
import pandas as pd

COLUMNS = [
    "timestamp", "hvac_status", "mode", "ambient_F", "setpoint_F",
    "humidity_%", "outdoor_F", "stove_F", "stove_fault", "stove_age_s",
]

# A stove reading is used only if the sensor reported no fault, the reading
# reached the sheet less than a minute before the row was logged (the Pico
# posts every ten seconds, so anything older means the Pico was offline),
# and the value is physically plausible.
MAX_AGE_S = 60
MIN_PLAUSIBLE_F = 40
MAX_PLAUSIBLE_F = 750

SEASON_END = "2026-05-15"


def load(path):
    book = pd.ExcelFile(path)
    parts = []
    for name in book.sheet_names:
        if name.startswith("oil_usage_20") and not name.endswith("chart"):
            tab = book.parse(name)
            parts.append(tab[[c for c in COLUMNS if c in tab.columns]])
    df = pd.concat(parts, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).drop_duplicates("timestamp")
    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ["ambient_F", "setpoint_F", "outdoor_F", "stove_F", "stove_fault", "stove_age_s"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["heating"] = (df["hvac_status"] == "HEATING").astype(float)
    df["stove_ok"] = (
        df["stove_F"].between(MIN_PLAUSIBLE_F, MAX_PLAUSIBLE_F)
        & (df["stove_fault"] == 0)
        & (df["stove_age_s"].abs() <= MAX_AGE_S)
    )
    return df


def season(df):
    """The heating season the analysis covers."""
    return df[df["timestamp"] < SEASON_END].copy()

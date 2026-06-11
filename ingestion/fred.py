"""
Fetch jet fuel price history from FRED (series WPSFD4111: PPI for Jet Fuel).
Saves monthly prices to data/processed/fuel_prices.parquet.

Requires FRED_API_KEY in .env at repo root.

Run: python -m ingestion.fred
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from fredapi import Fred

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

FRED_SERIES = "WPSFD4111"  # Producer Price Index: Jet Fuel
START_DATE = "2016-01-01"


def run() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise EnvironmentError("FRED_API_KEY not set — add it to .env at repo root.")

    print(f"Fetching {FRED_SERIES} from FRED (start={START_DATE})...")
    fred = Fred(api_key=api_key)
    raw = fred.get_series(FRED_SERIES, observation_start=START_DATE)

    df = raw.reset_index()
    df.columns = ["date", "jet_fuel_ppi"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna().reset_index(drop=True)

    # Cache raw copy alongside processed
    df.to_parquet(RAW_DIR / "fred_fuel.parquet", index=False)

    out = PROCESSED_DIR / "fuel_prices.parquet"
    df.to_parquet(out, index=False)
    print(f"Saved {len(df)} rows → {out}")
    print(df.tail(6).to_string())
    return df


if __name__ == "__main__":
    run()

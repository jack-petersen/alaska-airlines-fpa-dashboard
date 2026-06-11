"""
Download BTS T-100 International Segment data for Alaska Air (carrier AS) from SEA.
Filters to long-haul routes: SEA→FCO, SEA→KEF, SEA→ICN, SEA→NRT.
Also downloads DB1B fare data for the same routes.

Saves route data to data/processed/route_data.parquet.

Run: python -m ingestion.bts
"""

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

BTS_HEADERS = {
    "User-Agent": "FPA Dashboard johnhenrypetersen@gmail.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CARRIER = "AS"
ORIGIN = "SEA"
TARGET_DESTINATIONS = {"FCO", "KEF", "ICN", "NRT"}
START_YEAR = 2016

# BTS T-100 International Segment bulk download URL pattern
# One zip file per year containing all carriers' international segments
T100_URL_TEMPLATE = (
    "https://transtats.bts.gov/PREZIP/T_T100_SEGMENT_INT_CARRIER_{year}.zip"
)

# DB1B Coupon data (origin-destination fares) — quarterly zip
DB1B_URL_TEMPLATE = (
    "https://transtats.bts.gov/PREZIP/Origin_and_Destination_Survey_DB1BCoupon_{year}_Q{q}.zip"
)

# T-100 column names we want
T100_COLS = [
    "YEAR", "MONTH", "UNIQUE_CARRIER", "ORIGIN", "DEST",
    "PASSENGERS", "SEATS", "FREIGHT", "MAIL", "DISTANCE",
    "AIRCRAFT_TYPE", "DEPARTURES_PERFORMED",
]

# DB1B column names we want
DB1B_COLS = [
    "YEAR", "QUARTER", "ORIGIN", "DEST", "PASSENGERS", "MARKET_FARE",
]


def _download_t100_year(year: int) -> pd.DataFrame | None:
    cache_path = RAW_DIR / f"t100_int_{year}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    url = T100_URL_TEMPLATE.format(year=year)
    print(f"  Downloading T-100 {year}...")
    try:
        resp = requests.get(url, headers=BTS_HEADERS, timeout=120)
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"  Skipping {year}: {e}")
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(csv_name) as f:
            df = pd.read_csv(f, usecols=lambda c: c in T100_COLS, low_memory=False)

    df.columns = df.columns.str.upper()
    df.to_parquet(cache_path, index=False)
    return df


def _download_db1b_quarter(year: int, q: int) -> pd.DataFrame | None:
    cache_path = RAW_DIR / f"db1b_{year}_q{q}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    url = DB1B_URL_TEMPLATE.format(year=year, q=q)
    print(f"  Downloading DB1B {year} Q{q}...")
    try:
        resp = requests.get(url, headers=BTS_HEADERS, timeout=180)
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"  Skipping DB1B {year} Q{q}: {e}")
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(csv_name) as f:
            df = pd.read_csv(f, usecols=lambda c: c in DB1B_COLS, low_memory=False)

    df.columns = df.columns.str.upper()
    df.to_parquet(cache_path, index=False)
    return df


def _build_t100(current_year: int) -> pd.DataFrame:
    frames = []
    for year in range(START_YEAR, current_year + 1):
        df = _download_t100_year(year)
        if df is None:
            continue
        # Filter: Alaska Air from SEA to target destinations
        mask = (
            (df["UNIQUE_CARRIER"] == CARRIER)
            & (df["ORIGIN"] == ORIGIN)
            & (df["DEST"].isin(TARGET_DESTINATIONS))
        )
        subset = df[mask].copy()
        if not subset.empty:
            frames.append(subset)

    if not frames:
        raise RuntimeError("No T-100 records found for AS SEA routes — check URL or carrier code.")

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(
        result["YEAR"].astype(str) + "-" + result["MONTH"].astype(str).str.zfill(2) + "-01"
    )
    return result


def _build_db1b(current_year: int) -> pd.DataFrame:
    frames = []
    for year in range(START_YEAR, current_year + 1):
        for q in range(1, 5):
            df = _download_db1b_quarter(year, q)
            if df is None:
                continue
            # Filter to our routes (both directions for fare data)
            mask = (
                (df["ORIGIN"] == ORIGIN)
                & (df["DEST"].isin(TARGET_DESTINATIONS))
            ) | (
                (df["DEST"] == ORIGIN)
                & (df["ORIGIN"].isin(TARGET_DESTINATIONS))
            )
            subset = df[mask].copy()
            if not subset.empty:
                frames.append(subset)

    if not frames:
        print("  Warning: no DB1B fare data found — route revenue proxies will be T-100 only.")
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    # Normalize direction: always SEA as origin for consistency
    swap = result["DEST"] == ORIGIN
    result.loc[swap, ["ORIGIN", "DEST"]] = result.loc[swap, ["DEST", "ORIGIN"]].values
    return result


def _merge_t100_db1b(t100: pd.DataFrame, db1b: pd.DataFrame) -> pd.DataFrame:
    if db1b.empty:
        t100["avg_fare"] = None
        return t100

    fare_agg = (
        db1b.groupby(["YEAR", "QUARTER", "DEST"])
        .apply(lambda g: (g["MARKET_FARE"] * g["PASSENGERS"]).sum() / g["PASSENGERS"].sum())
        .reset_index(name="avg_fare")
    )
    fare_agg["MONTH"] = fare_agg["QUARTER"].map({1: 2, 2: 5, 3: 8, 4: 11})  # quarter midpoint

    merged = t100.merge(
        fare_agg[["YEAR", "MONTH", "DEST", "avg_fare"]],
        on=["YEAR", "MONTH", "DEST"],
        how="left",
    )
    return merged


def run() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    current_year = pd.Timestamp.now().year

    print("Building T-100 International Segment dataset...")
    t100 = _build_t100(current_year - 1)  # BTS lags ~1 year for finalized data
    print(f"  T-100: {len(t100)} route-months for AS SEA routes")

    print("Building DB1B fare dataset...")
    db1b = _build_db1b(current_year - 1)

    print("Merging T-100 + DB1B...")
    df = _merge_t100_db1b(t100, db1b)

    # Revenue proxy: passengers × avg_fare (where fare available)
    if "avg_fare" in df.columns:
        df["revenue_proxy"] = df["PASSENGERS"] * df["avg_fare"]

    out = PROCESSED_DIR / "route_data.parquet"
    df.to_parquet(out, index=False)
    print(f"Saved {len(df)} route-months → {out}")
    print(df[["date", "DEST", "PASSENGERS", "SEATS", "avg_fare"]].tail(8).to_string())
    return df


if __name__ == "__main__":
    run()

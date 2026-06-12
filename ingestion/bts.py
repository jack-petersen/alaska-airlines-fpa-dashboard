"""
Download BTS T-100 All-Carrier Segment data for Alaska Air (carrier AS) from SEA.
Shows Alaska's actual international + top domestic routes out of Seattle.

Uses the BTS form POST download (no pre-built PREZIP URLs exist for this table).
Downloads one year at a time, caches raw parquets in data/raw/bts/.

Saves: data/processed/route_data.parquet

Run: python -m ingestion.bts
"""

import io
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "bts"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

BTS_HEADERS = {
    "User-Agent": "FPA Dashboard johnhenrypetersen@gmail.com",
}

BTS_FORM_URL = (
    "https://www.transtats.bts.gov/DL_SelectFields.aspx"
    "?gnoyr_VQ=FMG&QO_fu146_anzr=Nv4+Pn44vr4+fgngvfgvpf"
)

CARRIER = "AS"
ORIGIN = "SEA"
START_YEAR = 2016

# Alaska's actual international destinations from SEA as of 2016–present
INTL_DESTINATIONS = {"KEF", "CUN", "PVR", "SJD", "GDL", "YVR", "SJO", "BZE", "MBJ", "MEX"}

# Top domestic routes from SEA for comparison
DOMESTIC_DESTINATIONS = {
    "ANC", "LAX", "SFO", "PDX", "JFK", "BOS", "ORD", "DEN",
    "ATL", "PHX", "SAN", "LAS", "HNL", "FAI",
}

TARGET_DESTINATIONS = INTL_DESTINATIONS | DOMESTIC_DESTINATIONS

T100_FIELDS = [
    "DEPARTURES_PERFORMED", "SEATS", "PASSENGERS",
    "UNIQUE_CARRIER", "UNIQUE_CARRIER_NAME",
    "ORIGIN", "DEST", "YEAR", "MONTH", "DISTANCE",
]


def _download_year(year: int, session: requests.Session) -> pd.DataFrame | None:
    """Download T-100 data for one full year via BTS form POST. Returns filtered Alaska rows."""
    cache = RAW_DIR / f"t100_as_sea_{year}.parquet"
    if cache.exists():
        print(f"  {year}: using cache")
        return pd.read_parquet(cache)

    print(f"  {year}: fetching form...")
    try:
        r = session.get(BTS_FORM_URL, headers=BTS_HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  {year}: form GET failed: {e}")
        return None

    soup = BeautifulSoup(r.text, "lxml")
    post_data: dict[str, str] = {}
    for inp in soup.find_all("input", type="hidden"):
        if inp.get("name"):
            post_data[inp["name"]] = inp.get("value", "")

    post_data["affiliate"] = "dot-bts"
    post_data["cboYear"] = str(year)
    post_data["cboPeriod"] = "All"
    post_data["__EVENTTARGET"] = ""
    post_data["__EVENTARGUMENT"] = ""
    post_data["btnDownload"] = "Download"
    for field in T100_FIELDS:
        post_data[field] = "on"

    print(f"  {year}: downloading (may take 30-90s)...")
    try:
        resp = session.post(BTS_FORM_URL, data=post_data, headers=BTS_HEADERS,
                            timeout=180, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  {year}: POST failed: {e}")
        return None

    content = b"".join(resp.iter_content(65536))
    if content[:4] != b"PK\x03\x04":
        print(f"  {year}: response is not a zip ({len(content)} bytes)")
        return None

    with zipfile.ZipFile(io.BytesIO(content)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(csv_name) as f:
            df = pd.read_csv(f, low_memory=False)

    df.columns = df.columns.str.upper()

    # Filter to Alaska from SEA immediately
    df = df[
        (df["UNIQUE_CARRIER"] == CARRIER)
        & (df["ORIGIN"] == ORIGIN)
    ].copy()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    print(f"  {year}: {len(df)} Alaska SEA routes cached")
    return df


def run() -> pd.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    current_year = pd.Timestamp.now().year
    # BTS data lags ~6 months; use prior year as safe upper bound
    end_year = current_year - 1

    session = requests.Session()
    frames = []

    print(f"Downloading BTS T-100 for AS SEA routes {START_YEAR}–{end_year}...")
    for year in range(START_YEAR, end_year + 1):
        df = _download_year(year, session)
        if df is not None and not df.empty:
            frames.append(df)
        time.sleep(1)  # be polite

    if not frames:
        raise RuntimeError("No T-100 data downloaded — check BTS connectivity.")

    combined = pd.concat(frames, ignore_index=True)

    # Filter to routes of interest (international + key domestic from SEA)
    routes = combined[combined["DEST"].isin(TARGET_DESTINATIONS)].copy()

    # Label route type
    routes["route_type"] = routes["DEST"].apply(
        lambda d: "International" if d in INTL_DESTINATIONS else "Domestic"
    )

    routes["date"] = pd.to_datetime(
        routes["YEAR"].astype(str) + "-" + routes["MONTH"].astype(str).str.zfill(2) + "-01"
    )

    # Load factor proxy (T-100 seats vs passengers)
    routes["load_factor"] = (routes["PASSENGERS"] / routes["SEATS"] * 100).clip(0, 100)

    out = PROCESSED_DIR / "route_data.parquet"
    routes.to_parquet(out, index=False)
    print(f"\nSaved {len(routes)} route-months → {out}")

    summary = (
        routes.groupby(["DEST", "route_type"])["PASSENGERS"]
        .sum()
        .sort_values(ascending=False)
        .head(20)
    )
    print("\nTop routes by total passengers (2016–present):")
    print(summary.to_string())

    return routes


if __name__ == "__main__":
    run()

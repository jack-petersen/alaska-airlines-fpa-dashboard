"""
Fetch Alaska Air Group operational statistics from EDGAR monthly traffic 8-K filings.
Alaska files monthly traffic stats (ASMs, RPMs, load factor, passengers) as 8-Ks.

Saves monthly stats to data/processed/traffic_stats.parquet.

Run: python -m ingestion.ir_pdfs
"""

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

CIK = "0000766421"
EDGAR_HEADERS = {"User-Agent": "FPA Dashboard johnhenrypetersen@gmail.com"}
START_YEAR = 2016

# Regex patterns for metric rows in traffic stat tables (handles various label formats)
METRIC_PATTERNS = {
    "asm": re.compile(r"available seat miles?", re.I),
    "rpm": re.compile(r"revenue passenger miles?", re.I),
    "load_factor": re.compile(r"passenger load factor|load factor", re.I),
    "passengers": re.compile(r"revenue passengers?", re.I),
    "departures": re.compile(r"airline departures?|departures?", re.I),
}

# Multipliers to normalize to raw units (ASMs/RPMs reported in millions or thousands)
UNIT_PATTERNS = {
    re.compile(r"\(000\)", re.I): 1_000,
    re.compile(r"\(millions?\)", re.I): 1_000_000,
    re.compile(r"\(000s?\)", re.I): 1_000,
}


def _fetch_submissions() -> dict:
    cache_path = RAW_DIR / "edgar_submissions.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    url = f"https://data.sec.gov/submissions/CIK{CIK}.json"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data))
    return data


def _get_traffic_8k_filings(submissions: dict) -> list[dict]:
    """Return list of {accn, filed, primaryDocument} for monthly traffic 8-Ks."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accns = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    descriptions = recent.get("primaryDocDescription", [])
    documents = recent.get("primaryDocument", [])
    items = recent.get("items", [])

    traffic_filings = []
    for form, accn, date, desc, doc, item in zip(
        forms, accns, dates, descriptions, documents, items
    ):
        if form != "8-K":
            continue
        year = int(date[:4])
        if year < START_YEAR:
            continue
        # Traffic stat 8-Ks are filed under item 7.01 (Reg FD) with "traffic" in description
        desc_lower = (desc or "").lower()
        item_str = str(item)
        if "traffic" in desc_lower or ("7.01" in item_str and "traffic" in desc_lower):
            traffic_filings.append({"accn": accn, "filed": date, "doc": doc})

    # Fallback: if description matching finds nothing, broaden to all 7.01 items
    if not traffic_filings:
        for form, accn, date, desc, doc, item in zip(
            forms, accns, dates, descriptions, documents, items
        ):
            if form != "8-K":
                continue
            year = int(date[:4])
            if year < START_YEAR:
                continue
            if "7.01" in str(item):
                traffic_filings.append({"accn": accn, "filed": date, "doc": doc})

    return traffic_filings


def _fetch_filing_html(accn: str, doc: str) -> str:
    accn_clean = accn.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{accn_clean}/{doc}"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _parse_number(text: str) -> float | None:
    """Extract numeric value from a table cell, handling commas and parentheses."""
    text = text.strip().replace(",", "").replace("%", "").replace(" pts", "")
    text = text.replace("(", "-").replace(")", "")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_traffic_html(html: str, filed: str) -> dict | None:
    """Extract system-level traffic metrics from one 8-K HTML document."""
    soup = BeautifulSoup(html, "lxml")

    # Find the table with ASM/RPM data — look for tables with >3 rows
    result: dict = {"filed": filed}
    found_any = False

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        # Determine column index for "current month" vs "prior year" — we want column 1
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True)

            for metric, pattern in METRIC_PATTERNS.items():
                if not pattern.search(label):
                    continue

                # Detect unit multiplier from label (e.g., "(millions)")
                multiplier = 1
                for unit_re, mult in UNIT_PATTERNS.items():
                    if unit_re.search(label):
                        multiplier = mult
                        break

                val = _parse_number(cells[1].get_text())
                if val is not None:
                    if metric in ("asm", "rpm", "passengers", "departures"):
                        result[metric] = val * multiplier
                    else:
                        result[metric] = val  # load_factor is a percent, no multiplier
                    found_any = True
                break

    return result if found_any else None


def _infer_period(filed: str, html: str) -> tuple[int, int] | None:
    """Infer the reporting month/year from filing date or document text."""
    # Traffic 8-Ks are filed 1-4 weeks after the reporting month ends
    filed_dt = pd.Timestamp(filed)

    # Look for explicit month/year in the HTML
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    text_lower = html[:5000].lower()
    for month_name, month_num in months.items():
        m = re.search(rf"{month_name}\s+(\d{{4}})", text_lower)
        if m:
            year = int(m.group(1))
            if 2010 <= year <= 2030:
                return year, month_num

    # Fallback: reporting month is the month before the filing date
    report_dt = filed_dt - pd.DateOffset(months=1)
    return report_dt.year, report_dt.month


def run() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching EDGAR submission list...")
    submissions = _fetch_submissions()

    filings = _get_traffic_8k_filings(submissions)
    print(f"Found {len(filings)} candidate traffic 8-Ks (from {START_YEAR}+)")

    rows = []
    for i, f in enumerate(filings):
        try:
            html = _fetch_filing_html(f["accn"], f["doc"])
            record = _parse_traffic_html(html, f["filed"])
            if record:
                period = _infer_period(f["filed"], html)
                if period:
                    record["year"], record["month"] = period
                    record["date"] = pd.Timestamp(year=period[0], month=period[1], day=1)
                    rows.append(record)
            time.sleep(0.11)  # EDGAR polite crawl rate: ≤10 req/s
        except Exception as e:
            print(f"  Skip {f['accn']}: {e}")

        if (i + 1) % 20 == 0:
            print(f"  Processed {i + 1}/{len(filings)}")

    if not rows:
        raise RuntimeError("No traffic stats parsed — check filing format or EDGAR connectivity.")

    df = pd.DataFrame(rows)
    df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
    df = df.reset_index(drop=True)

    out = PROCESSED_DIR / "traffic_stats.parquet"
    df.to_parquet(out, index=False)
    print(f"Saved {len(df)} months of traffic stats → {out}")
    print(df.tail(6).to_string())
    return df


if __name__ == "__main__":
    run()

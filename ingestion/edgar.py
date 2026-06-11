"""
Fetch Alaska Air Group (CIK 0000766421) financial data from SEC EDGAR XBRL API.
Saves quarterly income statement + key balance sheet items to data/processed/financials.parquet.

Design notes:
- EDGAR company facts include both quarterly (3-month) and YTD cumulative entries for the
  same fp code.  We keep only single-quarter (≈91 days) or full-year (≈365 days) durations.
- The same period can appear in multiple filings (current + comparative).  De-dup by (start,end)
  keeping the most recently filed value.
- Alaska switched from "Revenues" to "RevenueFromContractWithCustomerExcludingAssessedTax"
  in 2024.  We combine both series (non-overlapping by filing era) for a continuous history.

Run: python -m ingestion.edgar
"""

import json
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

CIK = "0000766421"
EDGAR_HEADERS = {"User-Agent": "FPA Dashboard johnhenrypetersen@gmail.com"}
START_YEAR = 2016

# Duration windows (days) for acceptable XBRL period types
QUARTER_DAYS = (70, 100)   # single fiscal quarter (~91 days)
ANNUAL_DAYS  = (355, 370)  # full fiscal year (~365 days)

# us-gaap concept names per field — ALL matched concepts are merged so eras with
# different naming conventions are combined into one continuous series.
CONCEPT_MAP: dict[str, list[str]] = {
    "revenue_total": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    ],
    "fuel_cost": [
        "AirlinesFuelCosts",
        "FuelCosts",
        "FuelCostsGrossOfHedging",
    ],
    "labor_cost": [
        "LaborAndRelatedExpense",
    ],
    "operating_expenses": [
        "OperatingExpenses",
        "CostsAndExpenses",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "net_income": [
        "NetIncomeLoss",
    ],
    "interest_expense": [
        "InterestExpense",
    ],
    "income_tax": [
        "IncomeTaxExpenseBenefit",
    ],
    "depreciation": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
    ],
    "total_assets": [
        "Assets",
    ],
    "long_term_debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
}


def _fetch_company_facts() -> dict:
    cache_path = RAW_DIR / "edgar_company_facts.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data))
    return data


def _extract_concept(usgaap: dict, concept: str) -> pd.DataFrame:
    """
    Extract clean quarterly time series for one us-gaap concept.

    Returns DataFrame with columns [start, end, val, filed_dt] for periods that are
    a single quarter or full year in duration.  YTD cumulative entries are dropped.
    """
    if concept not in usgaap:
        return pd.DataFrame()

    entries = usgaap[concept].get("units", {}).get("USD", [])
    if not entries:
        return pd.DataFrame()

    df = pd.DataFrame(entries)
    if "start" not in df.columns:
        # Instant items (balance sheet) have no start date — treat duration as 0
        df["start"] = df["end"]

    df = df[df["form"].isin(["10-K", "10-Q"])]
    df["period_end"] = pd.to_datetime(df["end"])
    df["period_start"] = pd.to_datetime(df["start"])
    df["duration"] = (df["period_end"] - df["period_start"]).dt.days
    df = df[df["period_end"].dt.year >= START_YEAR]

    # Keep only single-quarter and full-year durations (drop YTD cumulative entries)
    # Instant balance sheet items have duration=0 — always keep those
    is_quarter = df["duration"].between(*QUARTER_DAYS)
    is_annual  = df["duration"].between(*ANNUAL_DAYS)
    is_instant = df["duration"] == 0
    df = df[is_quarter | is_annual | is_instant]

    # De-duplicate: same (start, end) can appear in multiple filings as comparative data.
    # Keep the most recently filed value.
    df["filed_dt"] = pd.to_datetime(df["filed"])
    df = (
        df.sort_values("filed_dt")
        .drop_duplicates(subset=["period_start", "period_end"], keep="last")
    )

    return df[["period_start", "period_end", "val", "filed_dt"]].copy()


def _label_period(df: pd.DataFrame) -> pd.DataFrame:
    """Map period_end month to fiscal period label and fiscal year."""
    month_to_fp = {3: "Q1", 6: "Q2", 9: "Q3", 12: "FY"}
    df = df.copy()
    df["fp"] = df["period_end"].dt.month.map(month_to_fp)
    df["fy"] = df["period_end"].dt.year
    # Drop periods we can't label (non-standard quarter ends)
    df = df.dropna(subset=["fp"])
    return df


def _merge_concepts(usgaap: dict, concepts: list[str]) -> pd.DataFrame:
    """Extract and merge multiple concepts into one deduplicated time series."""
    frames = [_extract_concept(usgaap, c) for c in concepts]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    # Final dedup across merged concepts — prefer most recent filing
    combined = (
        combined.sort_values("filed_dt")
        .drop_duplicates(subset=["period_start", "period_end"], keep="last")
    )
    return combined


def _build_financials(facts: dict) -> pd.DataFrame:
    usgaap = facts.get("facts", {}).get("us-gaap", {})

    series: dict[str, pd.Series] = {}
    for field, concepts in CONCEPT_MAP.items():
        merged = _merge_concepts(usgaap, concepts)
        if merged.empty:
            continue
        labeled = _label_period(merged)
        if labeled.empty:
            continue
        series[field] = labeled.set_index(["fy", "fp", "period_end"])["val"]

    if not series:
        raise RuntimeError("No EDGAR concepts matched — check network / CIK.")

    df = pd.DataFrame(series).reset_index()

    # Raw USD → $M for all financial columns
    for col in CONCEPT_MAP:
        if col in df.columns:
            df[col] = df[col] / 1_000_000

    df = df.sort_values(["fy", "fp"]).reset_index(drop=True)
    return df


def run() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Alaska Air Group company facts from EDGAR...")
    facts = _fetch_company_facts()

    print("Extracting quarterly financial series...")
    df = _build_financials(facts)

    out = PROCESSED_DIR / "financials.parquet"
    df.to_parquet(out, index=False)
    print(f"Saved {len(df)} rows → {out}")
    print(df[["fy","fp","period_end","revenue_total","fuel_cost","operating_income","net_income"]].tail(16).to_string())
    return df


if __name__ == "__main__":
    run()

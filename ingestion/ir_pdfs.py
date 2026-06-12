"""
Fetch Alaska Air Group quarterly operating statistics and revenue breakdown
from earnings press releases (EX-99.1 exhibits on 8-K item 2.02 filings).

Produces two outputs:
  data/processed/traffic_stats.parquet   — ASMs, RPMs, RASM, CASMex, load factor, fuel
  data/processed/revenue_breakdown.parquet — passenger rev, Mileage Plan rev, cargo/other

Run: python -m ingestion.ir_pdfs
"""

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

CIK = "0000766421"
EDGAR_HEADERS = {"User-Agent": "FPA Dashboard johnhenrypetersen@gmail.com"}
START_YEAR = 2016

# ── Metric definitions ─────────────────────────────────────────────────────────
# Each entry: (output column, regex to match row label, unit multiplier, value type)
# value types: 'cents' (e.g. "17.30¢"), 'pct' (e.g. "86.5%"), 'num' (plain number)

METRICS = [
    ("passengers",           re.compile(r"revenue passengers", re.I),          1_000,     "num"),
    ("rpm",                  re.compile(r"RPMs?\s*\(000,000\)", re.I),          1_000_000, "num"),
    ("asm",                  re.compile(r"ASMs?\s*\(000,000\)", re.I),          1_000_000, "num"),
    ("load_factor",          re.compile(r"^load factor$", re.I),                1,         "pct"),
    ("yield_cents",          re.compile(r"^yield$", re.I),                      1,         "cents"),
    ("rasm",                 re.compile(r"^RASM$", re.I),                       1,         "cents"),
    ("casm_ex_fuel",         re.compile(r"CASMex|CASM excluding fuel", re.I),  1,         "cents"),
    ("fuel_cost_per_gallon", re.compile(r"economic fuel cost per gallon", re.I), 1,        "dollar"),
    ("fuel_gallons",         re.compile(r"fuel gallons\s*\(000,000\)", re.I),   1_000_000, "num"),
]


def _fetch_submissions() -> dict:
    cache = RAW_DIR / "edgar_submissions.json"
    if cache.exists():
        return json.loads(cache.read_text())
    url = f"https://data.sec.gov/submissions/CIK{CIK}.json"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    return data


def _find_earnings_filings(submissions: dict) -> list[dict]:
    """Return earnings 8-K filings (item 2.02) from START_YEAR to present."""
    r = submissions["filings"]["recent"]
    results = []
    for form, accn, date, item in zip(r["form"], r["accessionNumber"], r["filingDate"], r["items"]):
        if form == "8-K" and "2.02" in str(item) and int(date[:4]) >= START_YEAR:
            results.append({"accn": accn, "filed": date})
    return results


def _get_exhibit_url(accn: str) -> str | None:
    """Find the EX-99.1 exhibit URL in a filing's index."""
    accn_clean = accn.replace("-", "")
    idx_url = f"https://www.sec.gov/Archives/edgar/data/766421/{accn_clean}/"
    try:
        resp = requests.get(idx_url, headers=EDGAR_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    candidates: list[tuple[int, str]] = []  # (priority, url)

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "Archives" not in href or not href.endswith(".htm"):
            continue
        filename = href.split("/")[-1].lower()
        # Priority 1: explicit ex-99.1 exhibit (filename starts with ex991 or ex-99)
        if re.match(r"ex.?99.?1", filename):
            candidates.append((1, f"https://www.sec.gov{href}"))
        # Priority 2: filename contains "earnings" but is NOT the main 8-K cover
        elif "earnings" in filename and not filename.startswith("alk8") and not filename.startswith("alk-"):
            candidates.append((2, f"https://www.sec.gov{href}"))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _parse_value(cell: str, vtype: str) -> float | None:
    """Parse a table cell value based on its expected type."""
    cell = cell.strip()
    # Remove footnote markers like (a), (b), NM, —
    cell = re.sub(r"^\([a-z]\)$", "", cell).strip()
    if cell in ("—", "NM", "", "nm"):
        return None

    if vtype == "cents":
        # "17.30¢" or "17.30" (cents per ASM)
        m = re.search(r"([\d.]+)", cell.replace(",", ""))
        return float(m.group(1)) if m else None

    if vtype == "pct":
        # "86.5%" → 86.5
        m = re.search(r"([\d.]+)", cell.replace(",", ""))
        return float(m.group(1)) if m else None

    if vtype == "dollar":
        # "$3.66" → 3.66
        m = re.search(r"[\$]?\s*([\d.]+)", cell.replace(",", ""))
        return float(m.group(1)) if m else None

    if vtype == "num":
        # "16,349" → 16349
        m = re.search(r"([\d,]+)", cell.replace(",", ""))
        return float(m.group(1).replace(",", "")) if m else None

    return None


def _parse_ops_table(html: str) -> dict | None:
    """
    Find and parse the OPERATING STATISTICS SUMMARY table.
    Returns dict of metric → quarterly value (Three Months Ended column).
    """
    soup = BeautifulSoup(html, "lxml")
    target_table = None

    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if re.search(r"operating statistics summary", text, re.I) or (
            re.search(r"RASM", text) and re.search(r"ASMs?\s*\(000,000\)", text)
        ):
            target_table = table
            break

    if target_table is None:
        return None

    # Parse each row into a list of cell strings, filtering out empty/footnote-only rows
    rows: list[list[str]] = []
    for tr in target_table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)

    # Find which column is the "current quarter" value.
    # The header row typically has: [label_col, current_q, prior_q, change, current_ytd, ...]
    # We want column index 1 (0-indexed after label).
    # Skip rows that look like section headers or footnotes.
    result: dict = {}

    # Narrow to "Consolidated Operating Statistics" section only
    in_consolidated = False
    for row in rows:
        label = row[0]

        if re.search(r"consolidated operating statistics", label, re.I):
            in_consolidated = True
            continue
        if in_consolidated and re.search(r"(mainline|regional) operating statistics", label, re.I):
            break  # stop at mainline/regional sections

        if not in_consolidated:
            continue

        for col_name, pattern, multiplier, vtype in METRICS:
            # Strip footnote markers from label before matching
            clean_label = re.sub(r"\([a-z]\)", "", label).strip()
            if not pattern.search(clean_label):
                continue
            # Value is in the first data cell after the label (column index 1)
            if len(row) < 2:
                break
            # Some rows have a footnote marker as cell[1]; skip it
            val_idx = 1
            if len(row) > 2 and re.fullmatch(r"\([a-z]\)", row[val_idx].strip()):
                val_idx = 2
            val = _parse_value(row[val_idx], vtype)
            if val is not None and col_name not in result:
                if multiplier != 1:
                    result[col_name] = val * multiplier
                else:
                    result[col_name] = val
            break

    return result if result else None


def _parse_revenue_table(html: str) -> dict | None:
    """
    Extract quarterly revenue breakdown from the financial results table.

    Looks for a table containing 'Passenger revenue' and 'Mileage plan' rows.
    Returns dict with passenger_rev_m, mileage_plan_rev_m, cargo_other_rev_m,
    total_rev_m — all in $M.

    Table row formats vary by year:
      With $-cell:    ["Passenger revenue", "$", "2,615", ...]  → value at index 2
      Without $-cell: ["Mileage plan other revenue", "146", ...]  → value at index 1
    """
    soup = BeautifulSoup(html, "lxml")

    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if not (re.search(r"passenger revenue", text, re.I)
                and re.search(r"mileage plan", text, re.I)):
            continue

        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)

        result: dict = {}
        targets = {
            "passenger_rev_m":    re.compile(r"^passenger revenue$", re.I),
            "mileage_plan_rev_m": re.compile(r"mileage plan", re.I),
            "cargo_other_rev_m":  re.compile(r"cargo and other", re.I),
            "total_rev_m":        re.compile(r"total operating revenues?", re.I),
        }

        for row in rows:
            if not row:
                continue
            label = re.sub(r"\([a-z]\)", "", row[0]).strip()
            for col_name, pattern in targets.items():
                if col_name in result or not pattern.search(label):
                    continue
                # First data value: skip a lone "$" cell if present
                val_idx = 1
                if len(row) > 2 and row[val_idx].strip() in ("$", "$ "):
                    val_idx = 2
                if val_idx >= len(row):
                    break
                raw = row[val_idx].replace(",", "").replace("$", "").strip()
                try:
                    result[col_name] = float(raw)
                except ValueError:
                    pass
                break

        if "passenger_rev_m" in result:
            return result

    return None


def _infer_period_end(html: str, filed: str) -> pd.Timestamp | None:
    """Infer the period-end date from the press release header text."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # Look for "Three Months Ended [Month] [Day]," or "Quarter Ended ..."
    m = re.search(
        r"(?:three months|quarter)\s+ended\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        text, re.I
    )
    if m:
        try:
            return pd.to_datetime(f"{m.group(1)} {m.group(2)}, {m.group(3)}")
        except Exception:
            pass

    # Fallback: look for "Q[1-4] 20XX" in the title
    m2 = re.search(r"Q([1-4])\s+20(\d{2})", text)
    if m2:
        q, yr = int(m2.group(1)), int(m2.group(2)) + 2000
        month_map = {1: 3, 2: 6, 3: 9, 4: 12}
        return pd.Timestamp(year=yr, month=month_map[q], day=30 if month_map[q] in (6, 9) else 31)

    # Last resort: filing date minus ~3 weeks → approximate quarter end
    filed_dt = pd.Timestamp(filed)
    approx = filed_dt - pd.DateOffset(weeks=3)
    month_map = {1: 12, 2: 12, 3: 3, 4: 3, 5: 3, 6: 6, 7: 6, 8: 6, 9: 9, 10: 9, 11: 9, 12: 12}
    yr_adj = approx.year - (1 if approx.month == 12 and approx.month < filed_dt.month else 0)
    end_month = month_map[approx.month]
    end_day = 31 if end_month == 12 else (30 if end_month in (6, 9) else 31)
    return pd.Timestamp(year=yr_adj, month=end_month, day=end_day)


def run() -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading EDGAR submissions...")
    submissions = _fetch_submissions()

    earnings = _find_earnings_filings(submissions)
    print(f"Found {len(earnings)} quarterly earnings 8-Ks from {START_YEAR}+")

    ops_rows: list[dict] = []
    rev_rows: list[dict] = []

    for i, filing in enumerate(earnings):
        try:
            ex_url = _get_exhibit_url(filing["accn"])
            if ex_url is None:
                continue

            html = requests.get(ex_url, headers=EDGAR_HEADERS, timeout=30).text
            period_end = _infer_period_end(html, filing["filed"])
            if period_end is None:
                continue

            meta = {"period_end": period_end, "filed": filing["filed"]}

            stats = _parse_ops_table(html)
            if stats:
                ops_rows.append({**stats, **meta})

            rev = _parse_revenue_table(html)
            if rev:
                rev_rows.append({**rev, **meta})

            time.sleep(0.12)

        except Exception as e:
            print(f"  Skip {filing['accn']} ({filing['filed']}): {e}")

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(earnings)}")

    def _finalise(rows: list[dict], label: str) -> pd.DataFrame:
        if not rows:
            raise RuntimeError(f"No {label} parsed — check exhibit URL resolution.")
        df = pd.DataFrame(rows)
        df["period_end"] = pd.to_datetime(df["period_end"])
        df = df.sort_values("period_end").drop_duplicates(subset="period_end", keep="last")
        df["fy"] = df["period_end"].dt.year
        df["fp"] = df["period_end"].dt.month.map({3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"})
        return df.reset_index(drop=True)

    df_ops = _finalise(ops_rows, "operating stats")
    out_ops = PROCESSED_DIR / "traffic_stats.parquet"
    df_ops.to_parquet(out_ops, index=False)
    print(f"\nSaved {len(df_ops)} quarters of operating stats → {out_ops}")

    df_rev = _finalise(rev_rows, "revenue breakdown")
    out_rev = PROCESSED_DIR / "revenue_breakdown.parquet"
    df_rev.to_parquet(out_rev, index=False)
    print(f"Saved {len(df_rev)} quarters of revenue breakdown → {out_rev}")
    print(df_rev[["period_end","fp","passenger_rev_m","mileage_plan_rev_m",
                   "cargo_other_rev_m","total_rev_m"]].tail(8).to_string())

    return df_ops


if __name__ == "__main__":
    run()

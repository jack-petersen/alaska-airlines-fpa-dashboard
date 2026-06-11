# Alaska Airlines FP&A Dashboard

An internal-operator-style FP&A dashboard for Alaska Air Group (ALK), built as a finance portfolio project. Framed as a tool a finance team member at Alaska would use — not an external investor teardown.

Live app: *(coming soon — Streamlit Community Cloud)*

---

## What it does

- **Income Statement Overview** — Revenue, EBITDAR, net income; quarterly and annual with YoY change
- **Unit Economics** — RASM, CASM, CASM ex-fuel, load factor over time
- **Ancillary Revenue** — Mileage Plan and bag fee revenue as % of total
- **Fuel Analysis** — Fuel cost per gallon vs. market price, fuel as % of CASM
- **Scenario Planner** — Adjust fuel price, load factor, and hedge ratio; see real-time impact on CASM, EBITDAR, and cash
- **Route Analysis** — Operational performance for Alaska's new long-haul routes (SEA→FCO, SEA→KEF, SEA→ICN, SEA→NRT) using BTS T-100 and DB1B data

---

## Data sources

| Source | What it provides |
|--------|-----------------|
| [SEC EDGAR API](https://efts.sec.gov/LATEST/search-index?q=%22alaska+air%22&dateRange=custom&startdt=2015-01-01&enddt=2025-12-31&forms=10-K,10-Q) | 10-K/10-Q financial statements |
| Alaska IR supplemental PDFs | Unit economics: RASM, CASM, ASMs, load factor |
| [FRED API](https://fred.stlouisfed.org/) | Jet fuel price history |
| [BTS T-100 International](https://www.transtats.bts.gov/Tables.asp?QO_VQ=EFI&QO_anzr=Nv4yv0r%20b0-gvzr%20Cr4s14zn0pr%20Qn6n&QO_fu146_anzr=b0-gvzr) | Route-level passengers, seats, load factor (monthly) |
| [BTS DB1B](https://www.transtats.bts.gov/Tables.asp?QO_VQ=EEE&QO_anzr=b4vtv0%20n0q%20Qr56v0n6v10%20f748rl&QO_fu146_anzr=b4vtv0) | 10% ticket sample with fares (quarterly) |

---

## Tech stack

- **Python** — pandas, numpy, duckdb, requests, pdfplumber, fredapi
- **Dashboard** — Streamlit + Plotly
- **Storage** — DuckDB (analytical queries) + parquet (raw processed data)
- **Hosting** — Streamlit Community Cloud

---

## Project structure

```
ingestion/
  edgar.py        — pulls 10-K/10-Q financials from EDGAR API
  ir_pdfs.py      — parses Alaska IR supplemental operating stats PDFs
  fred.py         — jet fuel price history from FRED
  bts.py          — T-100 and DB1B route data from BTS
models/
  unit_economics.py  — RASM, CASM, CASM ex-fuel, load factor calculations
  scenarios.py       — scenario planning (fuel shock, hedge ratio, load factor)
  routes.py          — route-level revenue proxy and performance metrics
data/
  raw/            — cached API responses, PDFs, BTS CSVs (gitignored)
  processed/      — DuckDB file and parquet outputs (gitignored)
app.py            — Streamlit dashboard entry point
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Add your FRED API key (free at fred.stlouisfed.org)
echo "FRED_API_KEY=your_key_here" > .env

# Run ingestion
python -m ingestion.edgar
python -m ingestion.fred
python -m ingestion.bts

# Launch dashboard
streamlit run app.py
```

---

## Historical range

10 years: 2016–present. Captures pre-COVID baseline, 2020 crash, and recovery — makes the scenario planner and unit economics trends significantly more interesting.

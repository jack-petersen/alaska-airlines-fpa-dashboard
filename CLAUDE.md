# Alaska Airlines FP&A Dashboard

## What this is
A finance portfolio project — an internal-operator-style FP&A dashboard for Alaska Air Group (ALK). Framed as a tool a finance team member at Alaska would use. Built to demonstrate FP&A and data engineering skills for job applications. See PLAN.md for full build tracker and decisions.

## Tech stack
- **Python** — pandas, numpy, duckdb, requests, pdfplumber, fredapi
- **Dashboard** — Streamlit + Plotly
- **Storage** — DuckDB + parquet files in data/processed/
- **Hosting** — Streamlit Community Cloud (when ready)

## Project structure
```
ingestion/    — data fetching scripts (EDGAR, FRED, Alaska IR PDFs, BTS)
models/       — pure calculation functions (no I/O, no Streamlit)
data/raw/     — cached source data (gitignored)
data/processed/ — cleaned parquet / DuckDB (gitignored)
app.py        — Streamlit entry point
```

## Key rules
- Keep models/ pure — no I/O, no API calls, no Streamlit imports. Functions take DataFrames, return DataFrames or scalars.
- Ingestion scripts save to data/raw/ and data/processed/ — never hardcode paths, use pathlib relative to repo root.
- FRED API key lives in .env as FRED_API_KEY — never commit it.
- data/ is gitignored — always re-runnable from scratch via ingestion scripts.

## Data sources
| Module | Source | Notes |
|--------|--------|-------|
| `ingestion/edgar.py` | SEC EDGAR API | Alaska Air Group CIK: 0000766421 |
| `ingestion/ir_pdfs.py` | Alaska IR supplemental PDFs | Unit economics: RASM, CASM, ASMs, load factor |
| `ingestion/fred.py` | FRED API | Jet fuel series: WPSFD4111 |
| `ingestion/bts.py` | BTS T-100 International + DB1B | Route data for SEA→FCO, SEA→KEF, SEA→ICN, SEA→NRT |

## Historical range
2016–present (10 years). Captures pre-COVID, crash, and recovery.

## Build order
See PLAN.md. Current status: scaffold complete, ingestion layer is next.
Start with `ingestion/edgar.py`.

## Dashboard sections (in order)
1. Income Statement Overview
2. Unit Economics (RASM, CASM, CASM ex-fuel, load factor)
3. Ancillary Revenue (Mileage Plan, bag fees)
4. Fuel Analysis
5. Scenario Planner (fuel price ± %, load factor ± pts, hedge ratio)
6. Route Analysis — implement last (BTS T-100 + DB1B)

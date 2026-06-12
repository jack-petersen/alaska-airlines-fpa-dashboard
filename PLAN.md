# Project Plan & Build Tracker

## Status: Phase 3 complete — all 6 dashboard sections live

---

## Build order

### Phase 1 — Ingestion
- [x] `ingestion/edgar.py` — EDGAR XBRL company facts → quarterly financials.parquet
- [x] `ingestion/fred.py` — FRED WPSFD4111 → fuel_prices.parquet (requires .env FRED_API_KEY)
- [x] `ingestion/ir_pdfs.py` — EDGAR 8-K monthly traffic releases → traffic_stats.parquet (ASMs, RPMs, load factor, passengers)
- [x] `ingestion/bts.py` — BTS T-100 All-Carrier form POST → route_data.parquet (AS SEA hub, intl + domestic top routes)

### Phase 2 — Models
- [x] `models/unit_economics.py` — RASM, CASM, CASM ex-fuel, load factor, margins; add_q4() to derive Q4 from FY-Q1-Q2-Q3
- [x] `models/scenarios.py` — fuel shock, hedge ratio, load factor scenario functions

### Phase 3 — Dashboard (sections in order)
- [x] Section 1: Income Statement Overview
- [x] Section 2: Unit Economics
- [x] Section 3: Ancillary Revenue
- [x] Section 4: Fuel Analysis
- [x] Section 5: Scenario Planner
- [x] Section 6: Route Analysis

### Phase 4 — Deploy
- [ ] Connect repo to Streamlit Community Cloud
- [ ] Add live URL to README and job-hunt resume_base.md

---

## Key decisions

| Decision | Choice |
|----------|--------|
| Framing | Internal FP&A / operator view (not investor teardown) |
| Historical range | 10 years (2016–present) |
| Granularity | Quarterly for financials; monthly for BTS route data |
| Long-haul routes | SEA→FCO, SEA→KEF, SEA→ICN, SEA→NRT |
| Dashboard framework | Streamlit |
| Charts | Plotly |
| Storage | DuckDB + parquet |
| Hosting | Streamlit Community Cloud |

---

## Scenario planner inputs / outputs

**Inputs (sliders):**
- Fuel price ± %
- Load factor ± points
- Hedge ratio (% of consumption hedged at current price)

**Outputs (all update in real time):**
- CASM impact
- CASM ex-fuel (unchanged — shows fuel isolation)
- EBITDAR impact
- Estimated annual cash impact ($M)

---

## Route analysis notes
- Data source: BTS T-100 International segment file (not domestic)
- Revenue proxy = load factor × avg fare (DB1B) × seats
- Some routes may have sparse data if recently launched — handle gracefully
- Methodology note to be displayed in dashboard for transparency

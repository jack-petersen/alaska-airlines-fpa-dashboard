# Project Plan & Build Tracker

## Status: In progress — ingestion layer next

---

## Build order

### Phase 1 — Ingestion
- [ ] `ingestion/edgar.py` — pull Alaska Air Group 10-K/10-Q from EDGAR API, save to parquet
- [ ] `ingestion/fred.py` — pull jet fuel price history from FRED API
- [ ] `ingestion/ir_pdfs.py` — parse Alaska IR supplemental PDFs (RASM, CASM, ASMs, load factor)
- [ ] `ingestion/bts.py` — download and parse BTS T-100 international + DB1B route data

### Phase 2 — Models
- [ ] `models/unit_economics.py` — RASM, CASM, CASM ex-fuel, load factor calculations
- [ ] `models/scenarios.py` — fuel shock, hedge ratio, load factor scenario functions
- [ ] `models/routes.py` — route revenue proxy, load factor and fare trends by route

### Phase 3 — Dashboard (sections in order)
- [ ] Section 1: Income Statement Overview
- [ ] Section 2: Unit Economics
- [ ] Section 3: Ancillary Revenue
- [ ] Section 4: Fuel Analysis
- [ ] Section 5: Scenario Planner
- [ ] Section 6: Route Analysis (implement last)

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

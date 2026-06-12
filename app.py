"""
Alaska Air Group FP&A Dashboard
Streamlit entry point.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from models.unit_economics import add_q4
from models.scenarios import Baseline, run_scenario

PROCESSED = Path(__file__).parent / "data" / "processed"

st.set_page_config(
    page_title="Alaska Air Group — FP&A Dashboard",
    page_icon="✈",
    layout="wide",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.title("Alaska Air Group")
st.sidebar.caption("Internal FP&A Dashboard")

section = st.sidebar.radio(
    "Section",
    [
        "Income Statement Overview",
        "Unit Economics",
        "Ancillary Revenue",
        "Fuel Analysis",
        "Scenario Planner",
        "Route Analysis",
    ],
)

# ── Data loading ───────────────────────────────────────────────────────────────

@st.cache_data
def load_financials() -> pd.DataFrame:
    path = PROCESSED / "financials.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df = add_q4(df)
    df["period_end"] = pd.to_datetime(df["period_end"])
    return df


@st.cache_data
def load_fuel_prices() -> pd.DataFrame:
    path = PROCESSED / "fuel_prices.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data
def load_traffic() -> pd.DataFrame:
    path = PROCESSED / "traffic_stats.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["period_end"] = pd.to_datetime(df["period_end"])
    return df


financials = load_financials()
fuel_prices = load_fuel_prices()
traffic = load_traffic()

# ── Helpers ────────────────────────────────────────────────────────────────────

ALASKA_BLUE  = "#00205B"
ALASKA_GREEN = "#01426A"
ALASKA_TEAL  = "#0085CA"
ALASKA_GOLD  = "#E8B84B"
RED          = "#C8102E"

CHART_DEFAULTS = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font_color="#222",
    margin=dict(l=0, r=0, t=36, b=0),
    legend=dict(orientation="h", y=-0.15),
    hovermode="x unified",
)


def fmt_b(v: float) -> str:
    return f"${v/1000:.1f}B" if abs(v) >= 1000 else f"${v:.0f}M"


def metric_delta(current: float, prior: float) -> tuple[str, str]:
    if pd.isna(prior) or prior == 0:
        return "", "off"
    pct = (current - prior) / abs(prior) * 100
    sign = "+" if pct >= 0 else ""
    color = "normal" if pct >= 0 else "inverse"
    return f"{sign}{pct:.1f}%", color


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Income Statement Overview
# ══════════════════════════════════════════════════════════════════════════════
if section == "Income Statement Overview":
    st.title("Income Statement Overview")

    if financials.empty:
        st.error("No financial data found. Run `python -m ingestion.edgar` first.")
        st.stop()

    # ── Filters ────────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        year_range = st.slider(
            "Fiscal Year",
            min_value=int(financials["fy"].min()),
            max_value=int(financials["fy"].max()),
            value=(2016, int(financials["fy"].max())),
        )
    with col_f2:
        view = st.radio("View", ["Annual (FY)", "Quarterly"], horizontal=True)

    fp_filter = "FY" if view == "Annual (FY)" else ["Q1", "Q2", "Q3", "Q4"]
    df = financials[
        (financials["fy"] >= year_range[0])
        & (financials["fy"] <= year_range[1])
        & (financials["fp"].isin([fp_filter] if isinstance(fp_filter, str) else fp_filter))
    ].copy()

    x_col = "fy" if view == "Annual (FY)" else "period_end"
    x_label = "Fiscal Year" if view == "Annual (FY)" else "Period"

    # ── KPI cards ──────────────────────────────────────────────────────────────
    latest_fy = financials[financials["fp"] == "FY"].sort_values("fy").iloc[-1]
    prior_fy  = financials[financials["fp"] == "FY"].sort_values("fy").iloc[-2]

    k1, k2, k3, k4 = st.columns(4)

    rev_d, rev_c = metric_delta(latest_fy["revenue_total"], prior_fy["revenue_total"])
    k1.metric("Revenue (FY)", fmt_b(latest_fy["revenue_total"]), rev_d, delta_color=rev_c)

    oi_d, oi_c = metric_delta(latest_fy["operating_income"], prior_fy["operating_income"])
    k2.metric("Operating Income (FY)", fmt_b(latest_fy["operating_income"]), oi_d, delta_color=oi_c)

    ni_d, ni_c = metric_delta(latest_fy["net_income"], prior_fy["net_income"])
    k3.metric("Net Income (FY)", fmt_b(latest_fy["net_income"]), ni_d, delta_color=ni_c)

    op_margin = latest_fy["operating_income"] / latest_fy["revenue_total"] * 100
    op_margin_prior = prior_fy["operating_income"] / prior_fy["revenue_total"] * 100
    om_d = f"{op_margin - op_margin_prior:+.1f} pts"
    k4.metric("Operating Margin (FY)", f"{op_margin:.1f}%", om_d)

    st.divider()

    # ── Revenue waterfall / bar ────────────────────────────────────────────────
    c1, c2 = st.columns([3, 2])

    with c1:
        st.subheader("Revenue & Operating Income")
        fig = go.Figure()
        fig.add_bar(
            x=df[x_col], y=df["revenue_total"],
            name="Revenue", marker_color=ALASKA_TEAL,
        )
        fig.add_bar(
            x=df[x_col], y=df["operating_income"],
            name="Operating Income",
            marker_color=[ALASKA_GOLD if v >= 0 else RED for v in df["operating_income"]],
        )
        fig.update_layout(
            **CHART_DEFAULTS,
            barmode="overlay",
            yaxis_title="$M",
            xaxis_title=x_label,
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Net Income")
        fig2 = go.Figure()
        fig2.add_bar(
            x=df[x_col], y=df["net_income"],
            name="Net Income",
            marker_color=[ALASKA_GREEN if v >= 0 else RED for v in df["net_income"]],
        )
        fig2.update_layout(
            **CHART_DEFAULTS,
            yaxis_title="$M",
            xaxis_title=x_label,
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Cost breakdown ─────────────────────────────────────────────────────────
    st.subheader("Cost Composition")
    cost_cols = ["fuel_cost", "labor_cost", "depreciation"]
    cost_labels = {"fuel_cost": "Fuel", "labor_cost": "Labor", "depreciation": "D&A"}
    colors = [ALASKA_GOLD, ALASKA_TEAL, ALASKA_BLUE]

    fig3 = go.Figure()
    for col, color in zip(cost_cols, colors):
        if col in df.columns:
            fig3.add_bar(
                x=df[x_col], y=df[col],
                name=cost_labels[col],
                marker_color=color,
            )
    fig3.update_layout(
        **CHART_DEFAULTS,
        barmode="stack",
        yaxis_title="$M",
        xaxis_title=x_label,
    )
    st.plotly_chart(fig3, use_container_width=True)

    # ── Margins over time ──────────────────────────────────────────────────────
    df_pct = df.dropna(subset=["revenue_total", "operating_income", "net_income"]).copy()
    df_pct["op_margin"] = df_pct["operating_income"] / df_pct["revenue_total"] * 100
    df_pct["net_margin"] = df_pct["net_income"] / df_pct["revenue_total"] * 100

    if not df_pct.empty:
        st.subheader("Margins")
        fig4 = go.Figure()
        fig4.add_scatter(
            x=df_pct[x_col], y=df_pct["op_margin"],
            name="Operating Margin", mode="lines+markers",
            line=dict(color=ALASKA_TEAL, width=2),
        )
        fig4.add_scatter(
            x=df_pct[x_col], y=df_pct["net_margin"],
            name="Net Margin", mode="lines+markers",
            line=dict(color=ALASKA_GOLD, width=2),
        )
        fig4.add_hline(y=0, line_dash="dash", line_color="#aaa")
        fig4.update_layout(
            **CHART_DEFAULTS,
            yaxis_title="%",
            xaxis_title=x_label,
        )
        st.plotly_chart(fig4, use_container_width=True)

    # ── Raw data table ─────────────────────────────────────────────────────────
    with st.expander("Raw data"):
        show_cols = ["fy", "fp", "period_end", "revenue_total", "fuel_cost",
                     "labor_cost", "operating_expenses", "operating_income",
                     "net_income", "total_assets", "long_term_debt", "cash"]
        show_cols = [c for c in show_cols if c in df.columns]
        st.dataframe(
            df[show_cols].sort_values(["fy", "fp"]).reset_index(drop=True),
            use_container_width=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Unit Economics
# ══════════════════════════════════════════════════════════════════════════════
elif section == "Unit Economics":
    st.title("Unit Economics")

    if traffic.empty:
        st.error("No traffic data found. Run `python -m ingestion.ir_pdfs` first.")
        st.stop()

    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        year_range = st.slider(
            "Fiscal Year",
            min_value=int(traffic["fy"].min()),
            max_value=int(traffic["fy"].max()),
            value=(2016, int(traffic["fy"].max())),
            key="ue_years",
        )
    with col_f2:
        include_fy = st.checkbox("Include FY (annual) rows from financials", value=False)

    df_t = traffic[
        (traffic["fy"] >= year_range[0]) & (traffic["fy"] <= year_range[1])
    ].copy()

    # ── KPI cards ──────────────────────────────────────────────────────────────
    latest = df_t.sort_values("period_end").iloc[-1]
    prior  = df_t.sort_values("period_end").iloc[-2]

    k1, k2, k3, k4 = st.columns(4)

    def _delta(a, b):
        if pd.isna(a) or pd.isna(b) or b == 0:
            return "", "off"
        pct = (a - b) / abs(b) * 100
        return f"{pct:+.1f}%", "normal" if pct >= 0 else "inverse"

    r_d, r_c = _delta(latest["rasm"], prior["rasm"])
    k1.metric("RASM (latest qtr)", f"{latest['rasm']:.2f}¢", r_d, delta_color=r_c)

    c_d, c_c = _delta(latest["casm_ex_fuel"], prior["casm_ex_fuel"])
    k2.metric("CASMex (latest qtr)", f"{latest['casm_ex_fuel']:.2f}¢", c_d, delta_color=c_c)

    lf_d, lf_c = _delta(latest["load_factor"], prior["load_factor"])
    k3.metric("Load Factor (latest qtr)", f"{latest['load_factor']:.1f}%", lf_d, delta_color=lf_c)

    spread = latest["rasm"] - latest["casm_ex_fuel"]
    prior_spread = prior["rasm"] - prior["casm_ex_fuel"]
    sp_d, sp_c = _delta(spread, prior_spread)
    k4.metric("RASM − CASMex spread", f"{spread:.2f}¢", sp_d, delta_color=sp_c)

    st.divider()

    # ── RASM vs CASMex over time ───────────────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("RASM vs CASMex (¢ per ASM)")
        fig = go.Figure()
        fig.add_scatter(
            x=df_t["period_end"], y=df_t["rasm"],
            name="RASM", mode="lines+markers",
            line=dict(color=ALASKA_TEAL, width=2),
        )
        fig.add_scatter(
            x=df_t["period_end"], y=df_t["casm_ex_fuel"],
            name="CASMex", mode="lines+markers",
            line=dict(color=ALASKA_GOLD, width=2, dash="dash"),
        )
        fig.add_scatter(
            x=df_t["period_end"],
            y=df_t["rasm"] - df_t["casm_ex_fuel"],
            name="Spread (RASM−CASMex)",
            fill="tozeroy", fillcolor="rgba(0,133,202,0.10)",
            line=dict(color=ALASKA_BLUE, width=1),
        )
        fig.update_layout(**CHART_DEFAULTS, yaxis_title="¢ per ASM", xaxis_title="Quarter")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Passenger Load Factor (%)")
        fig2 = go.Figure()
        fig2.add_bar(
            x=df_t["period_end"], y=df_t["load_factor"],
            name="Load Factor",
            marker_color=[ALASKA_TEAL if v >= 80 else ALASKA_GOLD if v >= 70 else RED
                          for v in df_t["load_factor"]],
        )
        fig2.add_hline(y=80, line_dash="dot", line_color="#aaa",
                       annotation_text="80% threshold", annotation_position="top left")
        fig2.update_layout(**CHART_DEFAULTS, yaxis_title="%", xaxis_title="Quarter",
                           yaxis_range=[0, 100])
        st.plotly_chart(fig2, use_container_width=True)

    # ── Capacity (ASMs) and Traffic (RPMs) ────────────────────────────────────
    st.subheader("Capacity & Traffic (Billions of Miles)")
    fig3 = go.Figure()
    fig3.add_bar(
        x=df_t["period_end"], y=df_t["asm"] / 1e9,
        name="ASMs (capacity)", marker_color=ALASKA_BLUE, opacity=0.7,
    )
    fig3.add_bar(
        x=df_t["period_end"], y=df_t["rpm"] / 1e9,
        name="RPMs (traffic)", marker_color=ALASKA_TEAL, opacity=0.9,
    )
    fig3.update_layout(**CHART_DEFAULTS, barmode="overlay",
                       yaxis_title="Billions of Miles", xaxis_title="Quarter")
    st.plotly_chart(fig3, use_container_width=True)

    # ── Fuel efficiency ────────────────────────────────────────────────────────
    if "fuel_cost_per_gallon" in df_t.columns and df_t["fuel_cost_per_gallon"].notna().any():
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Economic Fuel Cost per Gallon ($)")
            fig4 = go.Figure()
            fig4.add_scatter(
                x=df_t["period_end"], y=df_t["fuel_cost_per_gallon"],
                mode="lines+markers", name="Fuel $/gal",
                line=dict(color=ALASKA_GOLD, width=2),
                fill="tozeroy", fillcolor="rgba(232,184,75,0.15)",
            )
            fig4.update_layout(**CHART_DEFAULTS, yaxis_title="$/gallon")
            st.plotly_chart(fig4, use_container_width=True)

        with c4:
            st.subheader("ASMs per Gallon (Fuel Efficiency)")
            if "fuel_gallons" in df_t.columns and df_t["fuel_gallons"].notna().any():
                df_t["asm_per_gallon"] = df_t["asm"] / df_t["fuel_gallons"]
                fig5 = go.Figure()
                fig5.add_scatter(
                    x=df_t["period_end"], y=df_t["asm_per_gallon"],
                    mode="lines+markers", name="ASMs/gallon",
                    line=dict(color=ALASKA_GREEN, width=2),
                )
                fig5.update_layout(**CHART_DEFAULTS, yaxis_title="ASMs per gallon")
                st.plotly_chart(fig5, use_container_width=True)

    # ── Raw data ───────────────────────────────────────────────────────────────
    with st.expander("Raw data"):
        st.dataframe(df_t.sort_values("period_end").reset_index(drop=True),
                     use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Fuel Analysis
# ══════════════════════════════════════════════════════════════════════════════
elif section == "Fuel Analysis":
    st.title("Fuel Analysis")

    if financials.empty or traffic.empty or fuel_prices.empty:
        st.error("Run `python -m ingestion.edgar`, `ingestion.ir_pdfs`, and `ingestion.fred` first.")
        st.stop()

    # ── Build quarterly fuel dataset ───────────────────────────────────────────
    fin_q = financials[financials["fp"].isin(["Q1", "Q2", "Q3", "Q4"])].copy()
    trf_q = traffic[["fy", "fp", "period_end", "fuel_cost_per_gallon", "fuel_gallons"]].copy()
    df_fuel = fin_q.merge(trf_q, on=["fy", "fp"], how="left", suffixes=("", "_t"))
    df_fuel["period_end"] = pd.to_datetime(df_fuel["period_end"])
    df_fuel = df_fuel.dropna(subset=["fuel_cost", "revenue_total"]).sort_values("period_end")

    df_fuel["fuel_pct_revenue"] = df_fuel["fuel_cost"] / df_fuel["revenue_total"] * 100
    df_fuel["fuel_pct_opex"] = (
        df_fuel["fuel_cost"] / df_fuel["operating_expenses"] * 100
    ).where(df_fuel["operating_expenses"].notna())

    year_range = st.slider(
        "Fiscal Year",
        min_value=int(df_fuel["fy"].min()),
        max_value=int(df_fuel["fy"].max()),
        value=(2017, int(df_fuel["fy"].max())),
        key="fuel_years",
    )
    df = df_fuel[(df_fuel["fy"] >= year_range[0]) & (df_fuel["fy"] <= year_range[1])]

    # ── KPI cards ──────────────────────────────────────────────────────────────
    has_gal = df["fuel_cost_per_gallon"].notna()
    latest_gal = df[has_gal].iloc[-1] if has_gal.any() else None
    prior_gal  = df[has_gal].iloc[-2] if has_gal.sum() >= 2 else None
    latest_rev = df.iloc[-1]
    prior_rev  = df.iloc[-2] if len(df) >= 2 else None

    k1, k2, k3, k4 = st.columns(4)

    if latest_gal is not None:
        gd = f"{(latest_gal['fuel_cost_per_gallon'] - prior_gal['fuel_cost_per_gallon']):+.2f}" if prior_gal is not None else ""
        gc = "inverse" if prior_gal is not None and latest_gal["fuel_cost_per_gallon"] > prior_gal["fuel_cost_per_gallon"] else "normal"
        k1.metric("Fuel Cost/Gallon", f"${latest_gal['fuel_cost_per_gallon']:.2f}", gd, delta_color=gc)

    fr_d = f"{(latest_rev['fuel_pct_revenue'] - prior_rev['fuel_pct_revenue']):+.1f} pts" if prior_rev is not None else ""
    fr_c = "inverse" if prior_rev is not None and latest_rev["fuel_pct_revenue"] > prior_rev["fuel_pct_revenue"] else "normal"
    k2.metric("Fuel % of Revenue", f"{latest_rev['fuel_pct_revenue']:.1f}%", fr_d, delta_color=fr_c)

    k3.metric("Fuel Spend (latest qtr)", f"${latest_rev['fuel_cost']:.0f}M")

    if latest_gal is not None and "fuel_gallons" in df.columns and pd.notna(latest_gal.get("fuel_gallons")):
        k4.metric("Gallons Consumed", f"{latest_gal['fuel_gallons']/1e6:.0f}M gal")

    st.divider()

    # ── Fuel cost per gallon + FRED PPI overlay ────────────────────────────────
    st.subheader("Alaska Fuel Cost/Gallon vs Jet Fuel PPI (FRED WPSFD4111)")
    st.caption("PPI normalized to $/gallon scale using Q4 2019 as base period — shows hedge effectiveness vs market.")

    # Normalize FRED PPI to $/gallon scale: anchor at a clean pre-COVID period
    fred = fuel_prices.copy()
    fred["date"] = pd.to_datetime(fred["date"])
    fred = fred[(fred["date"].dt.year >= year_range[0]) & (fred["date"].dt.year <= year_range[1])]

    # Find scaling factor: FRED PPI level vs Alaska's $/gallon in Q3 2019
    ref_alaska = df_fuel[df_fuel["period_end"].dt.to_period("Q") == pd.Period("2019Q3")]
    ref_fred   = fuel_prices[fuel_prices["date"].between("2019-07-01", "2019-09-30")]
    if not ref_alaska.empty and not ref_fred.empty and pd.notna(ref_alaska.iloc[0]["fuel_cost_per_gallon"]):
        scale = ref_alaska.iloc[0]["fuel_cost_per_gallon"] / ref_fred["jet_fuel_ppi"].mean()
        fred["market_price_est"] = fred["jet_fuel_ppi"] * scale
    else:
        scale = df_fuel["fuel_cost_per_gallon"].mean() / fred["jet_fuel_ppi"].mean()
        fred["market_price_est"] = fred["jet_fuel_ppi"] * scale

    fig_gal = go.Figure()
    fred_in_range = fred[(fred["date"].dt.year >= year_range[0]) & (fred["date"].dt.year <= year_range[1])]
    fig_gal.add_scatter(
        x=fred_in_range["date"], y=fred_in_range["market_price_est"],
        name="Jet Fuel PPI (market est.)", mode="lines",
        line=dict(color="#aaa", width=1.5, dash="dot"),
    )
    df_gal = df[df["fuel_cost_per_gallon"].notna()]
    fig_gal.add_scatter(
        x=df_gal["period_end"], y=df_gal["fuel_cost_per_gallon"],
        name="Alaska actual (hedged)", mode="lines+markers",
        line=dict(color=ALASKA_GOLD, width=2.5),
        marker=dict(size=7),
    )
    # Shade the gap between market and actual to illustrate hedge benefit/cost
    fig_gal.add_scatter(
        x=pd.concat([df_gal["period_end"], df_gal["period_end"][::-1]]),
        y=pd.concat([df_gal["fuel_cost_per_gallon"],
                     df_gal["period_end"].map(
                         fred_in_range.set_index(
                             fred_in_range["date"].dt.to_period("Q").map(str)
                         )["market_price_est"].reindex(
                             df_gal["period_end"].dt.to_period("Q").map(str)
                         ).fillna(method="ffill").values.__class__(
                             fred_in_range.set_index(
                                 fred_in_range["date"].dt.to_period("Q").map(str)
                             )["market_price_est"].reindex(
                                 df_gal["period_end"].dt.to_period("Q").map(str)
                             ).fillna(method="ffill")
                         )
                     )[::-1]]),
        fill="toself", fillcolor="rgba(232,184,75,0.12)",
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip",
    ) if False else None  # skip the complex fill — keep it clean

    fig_gal.update_layout(**CHART_DEFAULTS, yaxis_title="$/gallon", xaxis_title="")
    st.plotly_chart(fig_gal, use_container_width=True)

    # ── Fuel as % of revenue and % of opex ────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Fuel as % of Revenue")
        fig_pct = go.Figure()
        fig_pct.add_bar(
            x=df["period_end"], y=df["fuel_pct_revenue"],
            name="Fuel % Revenue",
            marker_color=[RED if v > 25 else ALASKA_GOLD if v > 20 else ALASKA_TEAL
                          for v in df["fuel_pct_revenue"]],
        )
        fig_pct.add_hline(y=25, line_dash="dot", line_color="#ccc",
                          annotation_text="25%", annotation_position="top right")
        fig_pct.update_layout(**CHART_DEFAULTS, yaxis_title="%", xaxis_title="",
                               yaxis_range=[0, df["fuel_pct_revenue"].max() * 1.15])
        st.plotly_chart(fig_pct, use_container_width=True)

    with c2:
        st.subheader("Total Fuel Spend ($M per quarter)")
        fig_spend = go.Figure()
        fig_spend.add_bar(
            x=df["period_end"], y=df["fuel_cost"],
            name="Fuel Cost $M",
            marker_color=ALASKA_GOLD,
        )
        fig_spend.update_layout(**CHART_DEFAULTS, yaxis_title="$M", xaxis_title="")
        st.plotly_chart(fig_spend, use_container_width=True)

    # ── Gallons consumed — operational scale ───────────────────────────────────
    df_gal2 = df[df["fuel_gallons"].notna()].copy()
    if not df_gal2.empty:
        st.subheader("Fuel Gallons Consumed (millions) — proxy for operational scale")
        fig_gal2 = go.Figure()
        fig_gal2.add_bar(
            x=df_gal2["period_end"], y=df_gal2["fuel_gallons"] / 1e6,
            name="Gallons (M)", marker_color=ALASKA_BLUE, opacity=0.8,
        )
        fig_gal2.update_layout(**CHART_DEFAULTS, yaxis_title="Million gallons", xaxis_title="")
        st.plotly_chart(fig_gal2, use_container_width=True)

    with st.expander("Raw data"):
        show = ["period_end", "fy", "fp", "fuel_cost", "revenue_total",
                "fuel_pct_revenue", "fuel_cost_per_gallon", "fuel_gallons"]
        show = [c for c in show if c in df.columns]
        st.dataframe(df[show].reset_index(drop=True), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Scenario Planner
# ══════════════════════════════════════════════════════════════════════════════
elif section == "Scenario Planner":
    st.title("Scenario Planner")
    st.caption("Model the P&L impact of fuel price shocks, load factor changes, and hedge coverage.")

    if traffic.empty or financials.empty:
        st.error("Run ingestion scripts first.")
        st.stop()

    # ── Build baseline options from quarters with complete data ────────────────
    fin_q = financials[financials["fp"].isin(["Q1","Q2","Q3","Q4"])].copy()
    trf_q = traffic.copy()
    merged = fin_q.merge(
        trf_q[["fy","fp","fuel_cost_per_gallon","fuel_gallons","asm",
               "yield_cents","load_factor","rasm","casm_ex_fuel"]],
        on=["fy","fp"], how="inner"
    ).dropna(subset=["fuel_cost_per_gallon","fuel_gallons","asm",
                     "yield_cents","rasm","casm_ex_fuel"])
    merged["period_end"] = pd.to_datetime(merged["period_end"])
    merged = merged.sort_values("period_end")

    if merged.empty:
        st.error("No quarters with complete data for scenario baseline.")
        st.stop()

    # Quarter selector
    quarter_labels = [
        f"{r.fy} {r.fp}  (RASM {r.rasm:.2f}¢, LF {r.load_factor:.1f}%, ${r.fuel_cost_per_gallon:.2f}/gal)"
        for r in merged.itertuples()
    ]
    default_idx = len(quarter_labels) - 1
    selected = st.selectbox("Baseline quarter", quarter_labels, index=default_idx)
    row = merged.iloc[quarter_labels.index(selected)]

    bl = Baseline(
        fuel_cost_per_gallon=row["fuel_cost_per_gallon"],
        fuel_gallons=row["fuel_gallons"],
        asm=row["asm"],
        yield_cents=row["yield_cents"],
        load_factor=row["load_factor"],
        rasm=row["rasm"],
        casm_ex_fuel=row["casm_ex_fuel"],
        operating_income_m=row.get("operating_income", 0) or 0,
        revenue_m=row["revenue_total"],
    )

    st.divider()

    # ── Sliders ────────────────────────────────────────────────────────────────
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        fuel_chg = st.slider("Fuel price change (%)", -50, +100, 0, step=5,
                             help="% change from baseline economic fuel cost/gallon")
    with col_s2:
        lf_delta = st.slider("Load factor (± pts)", -15, +15, 0, step=1,
                             help="Percentage-point change from baseline load factor")
    with col_s3:
        hedge = st.slider("Hedge ratio (%)", 0, 100, 0, step=5,
                          help="% of fuel consumption locked at baseline price (not exposed to price shock)") / 100

    result = run_scenario(bl, fuel_chg, lf_delta, hedge)

    st.divider()

    # ── KPI output cards ───────────────────────────────────────────────────────
    st.subheader("Scenario Output")

    def _color(v: float) -> str:
        return "normal" if v >= 0 else "inverse"

    def _sign(v: float) -> str:
        return f"+${abs(v):.0f}M" if v >= 0 else f"-${abs(v):.0f}M"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Annual Cash Impact",
        _sign(result.annual_cash_impact_m),
        delta_color=_color(result.annual_cash_impact_m),
    )
    k2.metric(
        "Quarterly Op. Income Δ",
        _sign(result.delta_operating_income_m),
        delta_color=_color(result.delta_operating_income_m),
    )
    k3.metric(
        "New RASM",
        f"{result.new_rasm:.2f}¢",
        f"{result.new_rasm - bl.rasm:+.2f}¢",
        delta_color=_color(result.new_rasm - bl.rasm),
    )
    k4.metric(
        "New CASM (total)",
        f"{result.new_casm:.2f}¢",
        f"{result.new_casm - (bl.casm_ex_fuel + bl.fuel_cost_per_gallon * bl.fuel_gallons / bl.asm * 100):+.2f}¢",
        delta_color=_color(-(result.new_casm - (bl.casm_ex_fuel + bl.fuel_cost_per_gallon * bl.fuel_gallons / bl.asm * 100))),
    )

    # ── Waterfall chart ────────────────────────────────────────────────────────
    st.subheader("P&L Impact Waterfall — Quarterly ($M)")

    baseline_oi = bl.operating_income_m
    fuel_bar    = result.fuel_contribution_m       # positive = benefit (e.g. fuel drops)
    lf_bar      = result.load_factor_contribution_m
    new_oi      = baseline_oi + result.delta_operating_income_m

    labels  = ["Baseline Op. Income", "Fuel Price Impact", "Load Factor Impact", "New Op. Income"]
    values  = [baseline_oi, fuel_bar, lf_bar, new_oi]
    colors  = [
        ALASKA_TEAL,
        RED if fuel_bar < 0 else ALASKA_GREEN,
        RED if lf_bar < 0 else ALASKA_GREEN,
        ALASKA_TEAL if new_oi >= 0 else RED,
    ]

    # Build waterfall manually so it renders cleanly
    measures = ["absolute", "relative", "relative", "total"]
    fig_wf = go.Figure(go.Waterfall(
        orientation="v",
        measure=measures,
        x=labels,
        y=values,
        connector=dict(line=dict(color="#ccc", width=1)),
        decreasing=dict(marker_color=RED),
        increasing=dict(marker_color=ALASKA_GREEN),
        totals=dict(marker_color=ALASKA_TEAL),
        text=[f"${v:+.0f}M" if i in (1,2) else f"${v:.0f}M" for i, v in enumerate(values)],
        textposition="outside",
    ))
    fig_wf.update_layout(
        **CHART_DEFAULTS,
        yaxis_title="$M",
        yaxis_zeroline=True,
        showlegend=False,
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    # ── Unit economics comparison table ───────────────────────────────────────
    st.subheader("Unit Economics: Baseline vs Scenario")
    comp = pd.DataFrame({
        "Metric": ["RASM (¢/ASM)", "CASM ex-fuel (¢/ASM)", "CASM total (¢/ASM)", "Load Factor (%)"],
        "Baseline": [
            f"{bl.rasm:.2f}¢",
            f"{bl.casm_ex_fuel:.2f}¢  ← unchanged",
            f"{bl.casm_ex_fuel + bl.fuel_cost_per_gallon * bl.fuel_gallons / bl.asm * 100:.2f}¢",
            f"{bl.load_factor:.1f}%",
        ],
        "Scenario": [
            f"{result.new_rasm:.2f}¢",
            f"{result.new_casm_ex_fuel:.2f}¢  ← unchanged",
            f"{result.new_casm:.2f}¢",
            f"{result.new_load_factor:.1f}%",
        ],
        "Delta": [
            f"{result.new_rasm - bl.rasm:+.2f}¢",
            "—",
            f"{result.new_casm - (bl.casm_ex_fuel + bl.fuel_cost_per_gallon * bl.fuel_gallons / bl.asm * 100):+.2f}¢",
            f"{lf_delta:+.1f} pts",
        ],
    })
    st.dataframe(comp, use_container_width=True, hide_index=True)

    # ── Methodology note ───────────────────────────────────────────────────────
    with st.expander("Methodology"):
        st.markdown(f"""
**Fuel shock:** Only the unhedged fraction `(1 − hedge ratio)` of gallons is exposed to the
price change. Delta fuel spend = baseline $/gal × gallons × (1 − hedge) × Δ%.

**Load factor shock:** Revenue changes via RASM = Yield × ΔLF/100. Incremental
passengers carry a {MARGINAL_COST_RATE:.0%} marginal cost rate (fuel, catering, fees),
so {1-MARGINAL_COST_RATE:.0%} flows to EBITDA.

**CASMex is explicitly held constant** — it reflects non-fuel unit costs (labor,
maintenance, overhead) which are not modelled here.

**Annual cash impact** = quarterly EBITDA delta × 4 (assumes conditions persist).
""")

# ══════════════════════════════════════════════════════════════════════════════
# PLACEHOLDER sections
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.title(section)
    st.info(f"**{section}** — coming soon. Run the relevant ingestion scripts first, then this section will be built out.")
    st.caption("Build order: Income Statement → Unit Economics → Ancillary → Fuel → Scenario → Routes")

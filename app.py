"""
Alaska Air Group FP&A Dashboard
Streamlit entry point.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from models.unit_economics import add_q4

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
# PLACEHOLDER sections
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.title(section)
    st.info(f"**{section}** — coming soon. Run the relevant ingestion scripts first, then this section will be built out.")
    st.caption("Build order: Income Statement → Unit Economics → Ancillary → Fuel → Scenario → Routes")

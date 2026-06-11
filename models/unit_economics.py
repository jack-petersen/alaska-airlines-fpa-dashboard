"""
Pure unit economics calculations for Alaska Air Group FP&A dashboard.
All functions: DataFrames in → DataFrame/scalar out. No I/O, no API calls.
"""

import numpy as np
import pandas as pd


def add_unit_economics(
    financials: pd.DataFrame,
    traffic: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join financial statement data with traffic stats and compute unit economics.

    financials: quarterly rows with columns [fy, fp, period_end, revenue_total,
                operating_expenses, fuel_cost, ...]
    traffic:    monthly rows with columns [date, year, month, asm, rpm, ...]

    Returns quarterly DataFrame with RASM, CASM, CASM ex-fuel, load_factor added.
    """
    # Aggregate traffic to quarterly
    traffic = traffic.copy()
    traffic["period_end"] = pd.to_datetime(traffic["date"])
    traffic["fy"] = traffic["period_end"].dt.year
    traffic["quarter"] = traffic["period_end"].dt.quarter
    traffic["fp"] = traffic["quarter"].map({1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
    # Annual: sum all four quarters
    traffic_q = (
        traffic.groupby(["fy", "fp"])[["asm", "rpm", "passengers"]]
        .sum()
        .reset_index()
    )
    # Add FY rows as sum of all quarters
    traffic_fy = (
        traffic.groupby("fy")[["asm", "rpm", "passengers"]]
        .sum()
        .reset_index()
        .assign(fp="FY")
    )
    traffic_all = pd.concat([traffic_q, traffic_fy], ignore_index=True)

    df = financials.merge(traffic_all, on=["fy", "fp"], how="left")

    # RASM = total revenue ($) / ASMs  → expressed in cents per ASM
    df["rasm"] = _safe_div(df["revenue_total"] * 1e6, df["asm"]) * 100

    # CASM = operating expenses ($) / ASMs  → cents per ASM
    df["casm"] = _safe_div(df["operating_expenses"] * 1e6, df["asm"]) * 100

    # CASM ex-fuel
    if "fuel_cost" in df.columns:
        df["casm_ex_fuel"] = _safe_div(
            (df["operating_expenses"] - df["fuel_cost"]) * 1e6, df["asm"]
        ) * 100

    # Load factor = RPMs / ASMs (%)
    df["load_factor"] = _safe_div(df["rpm"], df["asm"]) * 100

    # Operating margin
    if "operating_income" in df.columns:
        df["operating_margin"] = _safe_div(
            df["operating_income"], df["revenue_total"]
        ) * 100

    # Net margin
    if "net_income" in df.columns:
        df["net_margin"] = _safe_div(df["net_income"], df["revenue_total"]) * 100

    return df


def add_q4(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive Q4 figures from FY - Q1 - Q2 - Q3 for income statement line items.
    Returns df with Q4 rows appended.
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    exclude = ["fy"]
    flow_cols = [c for c in numeric_cols if c not in exclude]

    q4_rows = []
    for fy, grp in df.groupby("fy"):
        fy_row = grp[grp["fp"] == "FY"]
        q_rows = grp[grp["fp"].isin(["Q1", "Q2", "Q3"])]
        if fy_row.empty or len(q_rows) < 3:
            continue

        q4 = {"fy": fy, "fp": "Q4"}
        q4["period_end"] = pd.Timestamp(year=fy, month=12, day=31)
        for col in flow_cols:
            fy_val = fy_row[col].iloc[0]
            q_sum = q_rows[col].sum()
            q4[col] = fy_val - q_sum if pd.notna(fy_val) else np.nan
        q4_rows.append(q4)

    if not q4_rows:
        return df

    result = pd.concat([df, pd.DataFrame(q4_rows)], ignore_index=True)
    fp_order = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}
    result["_fp_ord"] = result["fp"].map(fp_order)
    result = result.sort_values(["fy", "_fp_ord"]).drop(columns="_fp_ord")
    return result.reset_index(drop=True)


def fuel_cost_per_gallon(
    financials: pd.DataFrame,
    gallons_consumed: pd.Series,
) -> pd.Series:
    """Return implied fuel cost per gallon ($) given cost ($M) and gallons consumed."""
    return (financials["fuel_cost"] * 1e6) / gallons_consumed


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide two Series, returning NaN where denominator is zero or NaN."""
    return numerator.div(denominator.replace(0, np.nan))

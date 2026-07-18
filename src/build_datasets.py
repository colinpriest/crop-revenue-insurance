"""Build the two county-year panel datasets defined in specs/data-specs.md.

Dataset 1 (replication window)
    data/processed/corn_grip_panel_1975_2009.(parquet|csv)
    - years 1975-2009, only counties with a complete 35-year yield record
      (mirrors the paper's n=35 per county; paper sample = 602 counties)
    - linear county trends fitted on 1975-2009

Dataset 2 (extended window)
    data/processed/corn_grip_panel_extended.(parquet|csv)
    - all counties/years 1975-latest with both yield and price available
    - two trend versions: fitted on 1975-2009 and fitted on the full sample
    - dataset_version flag: "original_window_1975_2009" for rows in
      1975-2009, "extended_window" for later years

Auxiliary tables
    data/processed/county_trend_params.csv
    data/processed/aph_table.csv

Variable definitions follow specs section 5.1; see docs/data-dictionary.md.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
PROC = os.path.join(ROOT, "data", "processed")

REPL_START, REPL_END = 1975, 2009
COVERAGES = [0.65, 0.75, 0.85, 0.90]   # paper uses all four; spec 4.2 lists only 0.65
LEVERAGE = 1.5                          # paper's GRIP-HR leverage factor


def fit_trends(df: pd.DataFrame, lo: int, hi: int, label: str) -> pd.DataFrame:
    """Per-county OLS of yield on t = year - lo, using years lo..hi."""
    rows = []
    for fips, g in df[(df.year >= lo) & (df.year <= hi)].groupby("fips5"):
        t = g.year.to_numpy(float) - lo
        y = g.yield_bu_acre.to_numpy(float)
        if len(g) < 3:
            continue
        beta, alpha = np.polyfit(t, y, 1)
        rows.append((fips, alpha, beta, len(g), label))
    return pd.DataFrame(rows, columns=["fips5", "alpha", "beta", "n_obs", "trend_window"])


def add_trend_cols(panel: pd.DataFrame, trends: pd.DataFrame, lo: int,
                   suffix: str = "") -> pd.DataFrame:
    m = panel.merge(trends[["fips5", "alpha", "beta"]], on="fips5", how="inner")
    t = m.year - lo
    m[f"yield_trend{suffix}"] = m.alpha + m.beta * t
    m[f"yield_resid{suffix}"] = m.yield_bu_acre - m[f"yield_trend{suffix}"]      # option A
    m[f"yield_ratio{suffix}"] = m.yield_bu_acre / m[f"yield_trend{suffix}"]      # option B
    return m.drop(columns=["alpha", "beta"])


def add_insurance_cols(panel: pd.DataFrame, aph: pd.Series) -> pd.DataFrame:
    panel = panel.merge(aph.rename("aph"), left_on="fips5", right_index=True)
    panel["revenue"] = panel.yield_bu_acre * panel.price_harvest
    pmax = np.maximum(panel.price_base, panel.price_harvest)
    for cov in COVERAGES:
        tag = f"{int(cov * 100)}"
        panel[f"guarantee_hr_{tag}"] = pmax * panel.aph * cov
        panel[f"indemnity_hr_{tag}"] = LEVERAGE * np.maximum(
            0.0, panel[f"guarantee_hr_{tag}"] - panel.revenue)
    return panel


def save(df: pd.DataFrame, stem: str) -> None:
    csv_path = os.path.join(PROC, stem + ".csv")
    df.to_csv(csv_path, index=False, float_format="%.6f")
    try:
        df.to_parquet(os.path.join(PROC, stem + ".parquet"), index=False)
    except Exception as e:                                    # pyarrow missing
        print(f"  (parquet skipped for {stem}: {e})")
    print(f"  wrote {stem}: {len(df):,} rows, "
          f"{df.fips5.nunique()} counties, years {df.year.min()}-{df.year.max()}")


def main() -> None:
    os.makedirs(PROC, exist_ok=True)
    yields = pd.read_csv(os.path.join(RAW, "nass_county_corn_yields.csv"),
                         dtype={"state_fips": str, "county_fips": str})
    yields["fips5"] = yields.state_fips.str.zfill(2) + yields.county_fips.str.zfill(3)
    prices = pd.read_csv(os.path.join(PROC, "price_summary.csv"))

    # ------------------------------------------------------------- Dataset 1
    win = yields[(yields.year >= REPL_START) & (yields.year <= REPL_END)]
    counts = win.groupby("fips5").year.nunique()
    complete = counts[counts == REPL_END - REPL_START + 1].index
    d1 = win[win.fips5.isin(complete)].copy()
    trends1 = fit_trends(d1, REPL_START, REPL_END, f"{REPL_START}_{REPL_END}")
    d1 = add_trend_cols(d1, trends1, REPL_START)
    d1 = d1.merge(prices, on="year", how="inner")
    aph1 = d1.groupby("fips5").yield_bu_acre.mean()           # paper: APH = mean county yield
    d1 = add_insurance_cols(d1, aph1)
    d1["dataset_version"] = "original_window_1975_2009"
    d1 = d1.sort_values(["fips5", "year"]).reset_index(drop=True)
    save(d1, "corn_grip_panel_1975_2009")

    # ------------------------------------------------------------- Dataset 2
    d2 = yields.copy()
    trends_full = fit_trends(d2, REPL_START, int(d2.year.max()),
                             f"{REPL_START}_{int(d2.year.max())}")
    d2 = add_trend_cols(d2, trends_full, REPL_START)              # full-sample trend
    d2 = d2.merge(trends1[["fips5", "alpha", "beta"]], on="fips5", how="left")
    t = d2.year - REPL_START
    d2["yield_trend_7509"] = d2.alpha + d2.beta * t               # original-window trend
    d2["yield_resid_7509"] = d2.yield_bu_acre - d2.yield_trend_7509
    d2["yield_ratio_7509"] = d2.yield_bu_acre / d2.yield_trend_7509
    d2 = d2.drop(columns=["alpha", "beta"])
    d2 = d2.merge(prices, on="year", how="inner")
    aph2 = d2.groupby("fips5").yield_bu_acre.mean()
    d2 = add_insurance_cols(d2, aph2)
    d2["dataset_version"] = np.where(d2.year <= REPL_END,
                                     "original_window_1975_2009", "extended_window")
    d2 = d2.sort_values(["fips5", "year"]).reset_index(drop=True)
    save(d2, "corn_grip_panel_extended")

    # ------------------------------------------------------ auxiliary tables
    meta = yields[["fips5", "state_fips", "county_fips", "state_alpha",
                   "county_name"]].drop_duplicates("fips5")
    tp = pd.concat([trends1, trends_full]).merge(meta, on="fips5")
    tp.rename(columns={"alpha": "alpha_c", "beta": "beta_c"}, inplace=True)
    tp.to_csv(os.path.join(PROC, "county_trend_params.csv"), index=False,
              float_format="%.6f")

    aph_tbl = aph1.rename("aph_1975_2009").to_frame().merge(
        meta.set_index("fips5"), left_index=True, right_index=True)
    for cov in COVERAGES:
        aph_tbl[f"guarantee_base_{int(cov*100)}"] = 4.0 * aph_tbl.aph_1975_2009 * cov
    aph_tbl.reset_index().rename(columns={"index": "fips5"}).to_csv(
        os.path.join(PROC, "aph_table.csv"), index=False, float_format="%.6f")
    print("  wrote county_trend_params.csv and aph_table.csv")


if __name__ == "__main__":
    main()

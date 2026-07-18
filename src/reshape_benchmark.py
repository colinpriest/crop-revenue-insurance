"""Reshape the panel into tabular-synthetic-data benchmark formats (Task-2 plan).

Separate from the replication pipeline: reads the existing processed panels,
writes only under data/benchmark/, and never modifies data/processed or
results/.

Two tracks (see docs/benchmark-schema.md):

  Track A  - one row per YEAR (the independent replication unit). Spatial units
             become columns of detrended-yield residuals. Built at three
             resolutions on a ladder:
               state   (K=8,   sanity tier,  n > p)
               asd     (K~50,  PRIMARY tier, p ~ n)
               county  (K~600, STRESS tier,  p >> n)
             Files: panel_wide_<res>.csv  + units_<res>.csv (+ trend sidecars)

  Track B  - one row per COUNTY-YEAR (high-n tier for DL / marginal & TSTR
             utility metrics), with spatial features (lat/lon/asd) and the
             year-level shared price variables kept explicit so hierarchical
             generators can condition on them.
             File: panel_long.csv

Downstream target: indemnity at 90% coverage (most tail-sensitive; default).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
BENCH = os.path.join(ROOT, "data", "benchmark")

TARGET_COV = 0.90          # default downstream target coverage (plan item)
LEVERAGE = 1.5
BASE_PRICE = 4.0

# resolution ladder: label -> (grouping columns, tier note)
LADDER = {
    "state": ("state_fips", "sanity tier (K=8, n>p)"),
    "asd": ("asd5", "PRIMARY tier (K~50, p~n)"),
    "county": ("fips5", "STRESS tier (K~600, p>>n)"),
}


def load_panel() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(PROC, "corn_grip_panel_extended.csv"),
                     dtype={"fips5": str, "state_fips": str, "county_fips": str})
    # 5-digit ASD key (state + 2-digit district) for a stable spatial-unit id
    df["asd5"] = df.state_fips.str.zfill(2) + df.asd_code.astype(int).astype(str).str.zfill(3)
    cent = pd.read_csv(os.path.join(BENCH, "county_centroids.csv"),
                       dtype={"fips5": str})
    return df.merge(cent[["fips5", "lat", "lon", "spatial_order"]],
                    on="fips5", how="left")


def refit_unit_trend(sub: pd.DataFrame) -> pd.DataFrame:
    """Per spatial-unit OLS linear yield trend on t=year-1975; return residuals.

    For aggregated units (state/asd) the trend is fitted on the acreage-unweighted
    mean county yield of the unit, so residuals are a clean detrended series.
    """
    g = sub.groupby("year", as_index=False).yield_bu_acre.mean()
    t = g.year.to_numpy(float) - 1975
    beta, alpha = np.polyfit(t, g.yield_bu_acre.to_numpy(float), 1)
    g["yield_trend"] = alpha + beta * t
    g["y_resid"] = g.yield_bu_acre - g.yield_trend
    g["alpha"], g["beta"] = alpha, beta
    return g


def build_wide(panel: pd.DataFrame, res: str) -> None:
    key, note = LADDER[res]
    prices = panel[["year", "price_base", "price_pctchg"]].drop_duplicates("year")

    resid_wide, units, trend_rows = {}, [], []
    meta_cols = ["state_fips", "state_alpha"] if key != "state" else ["state_alpha"]
    for uid, sub in panel.groupby(key):
        g = refit_unit_trend(sub)
        col = f"y_resid_{uid}"
        resid_wide[col] = g.set_index("year").y_resid
        first = sub.iloc[0]
        units.append({
            "unit_id": uid, "column": col, "resolution": res,
            "n_counties": sub.fips5.nunique(),
            "lat": sub.lat.mean(), "lon": sub.lon.mean(),
            "spatial_order": sub.spatial_order.mean(),
            **{c: first[c] for c in meta_cols},
        })
        trend_rows.append({"unit_id": uid, "resolution": res,
                           "alpha": g.alpha.iloc[0], "beta": g.beta.iloc[0]})

    umeta = pd.DataFrame(units).sort_values("spatial_order").reset_index(drop=True)
    ordered_cols = umeta.column.tolist()                       # serpentine order
    wide = pd.DataFrame(resid_wide).reindex(columns=ordered_cols)
    wide = prices.set_index("year").join(wide, how="inner").reset_index()
    wide = wide.sort_values("year").reset_index(drop=True)

    wide.to_csv(os.path.join(BENCH, f"panel_wide_{res}.csv"), index=False,
                float_format="%.5f")
    umeta.to_csv(os.path.join(BENCH, f"units_{res}.csv"), index=False,
                 float_format="%.5f")
    pd.DataFrame(trend_rows).to_csv(
        os.path.join(BENCH, f"trend_params_{res}.csv"), index=False,
        float_format="%.6f")
    print(f"  panel_wide_{res}.csv: {wide.shape[0]} rows x {wide.shape[1]} cols "
          f"(1 year/row, K={len(ordered_cols)} units) - {note}")


def build_long(panel: pd.DataFrame) -> None:
    cov = TARGET_COV
    tag = f"{int(cov*100)}"
    df = panel.copy()
    pmax = np.maximum(df.price_base, df.price_harvest)
    df["guarantee"] = pmax * df.aph * cov
    df["revenue_actual"] = df.yield_bu_acre * df.price_harvest
    # downstream TARGET: GRIP-HR pure premium at 90% (protection-scaled form)
    df[f"indemnity_{tag}"] = LEVERAGE / cov * np.maximum(0.0, df.guarantee - df.revenue_actual)

    cols = ["fips5", "state_fips", "state_alpha", "county_name", "asd5",
            "lat", "lon", "spatial_order", "year",
            # year-level shared latents (for hierarchical/conditional generation)
            "price_base", "price_harvest", "price_pctchg",
            # county stochastic core + marginal
            "yield_bu_acre", "yield_resid", "aph",
            # derived / target
            "revenue_actual", "guarantee", f"indemnity_{tag}"]
    out = df[cols].sort_values(["fips5", "year"]).reset_index(drop=True)
    out.to_csv(os.path.join(BENCH, "panel_long.csv"), index=False,
               float_format="%.5f")
    print(f"  panel_long.csv: {out.shape[0]} rows x {out.shape[1]} cols "
          f"(1 county-year/row; target=indemnity_{tag})")


def main() -> None:
    os.makedirs(BENCH, exist_ok=True)
    panel = load_panel()
    print(f"loaded extended panel: {len(panel)} county-years, "
          f"{panel.fips5.nunique()} counties, {panel.year.nunique()} years")
    print("Track A (year = row):")
    for res in LADDER:
        build_wide(panel, res)
    print("Track B (county-year = row):")
    build_long(panel)


if __name__ == "__main__":
    main()

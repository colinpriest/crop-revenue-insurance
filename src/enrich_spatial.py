"""Attach spatial reference data to the benchmark counties (Task-2 plan, item 1).

Produces two generator-consumable representations of "what is adjacent":

  data/benchmark/county_centroids.csv  - centroid lat/lon per county (numeric
                                         features any generator can ingest)
  data/benchmark/county_adjacency.csv  - shared-border edge list (graph form)

Inputs (Census, downloaded into data/raw/spatial/):
  2023_Gaz_counties_national.txt  - Gazetteer county centroids (INTPTLAT/LONG)
  county_adjacency.txt            - Census county-adjacency reference file

Only the 8 Midwest states / counties present in the yield panel are kept.
This script does NOT touch the existing replication data or results.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
SPATIAL = os.path.join(RAW, "spatial")
OUT = os.path.join(ROOT, "data", "benchmark")


def panel_fips() -> set[str]:
    y = pd.read_csv(os.path.join(RAW, "nass_county_corn_yields.csv"),
                    dtype={"state_fips": str, "county_fips": str})
    return set((y.state_fips.str.zfill(2) + y.county_fips.str.zfill(3)).unique())


def build_centroids(keep: set[str]) -> pd.DataFrame:
    gaz = pd.read_csv(os.path.join(SPATIAL, "2023_Gaz_counties_national.txt"),
                      sep="\t", dtype={"GEOID": str})
    gaz.columns = [c.strip() for c in gaz.columns]
    gaz["fips5"] = gaz.GEOID.str.zfill(5)
    df = gaz[gaz.fips5.isin(keep)][["fips5", "USPS", "NAME",
                                    "INTPTLAT", "INTPTLONG"]].copy()
    df.columns = ["fips5", "state_alpha", "county_name", "lat", "lon"]
    df["lat"] = df.lat.astype(float)
    df["lon"] = df.lon.astype(float)
    return df.sort_values("fips5").reset_index(drop=True)


def build_adjacency(keep: set[str]) -> pd.DataFrame:
    """Parse the Census fixed-record adjacency file into an undirected edge list."""
    edges = []
    cur = None
    with open(os.path.join(SPATIAL, "county_adjacency.txt"),
              encoding="latin-1") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            # rows are: [name, fips, neighbor_name, neighbor_fips] where the
            # first two are blank on continuation lines for the same county
            if len(parts) < 4:
                continue
            if parts[1].strip():
                cur = parts[1].strip().zfill(5)
            nb = parts[3].strip().zfill(5)
            if cur and nb and cur != nb:
                edges.append((cur, nb))
    e = pd.DataFrame(edges, columns=["fips5", "neighbor_fips5"])
    e = e[e.fips5.isin(keep) & e.neighbor_fips5.isin(keep)]
    # canonicalise unordered pairs and drop duplicates
    a = np.minimum(e.fips5, e.neighbor_fips5)
    b = np.maximum(e.fips5, e.neighbor_fips5)
    return (pd.DataFrame({"fips5": a, "neighbor_fips5": b})
            .drop_duplicates().sort_values(["fips5", "neighbor_fips5"])
            .reset_index(drop=True))


def snake_order(cent: pd.DataFrame) -> pd.DataFrame:
    """Serpentine spatial ordering so adjacent columns are geographically near:
    bin latitude into rows, sort each row by longitude, alternating direction."""
    df = cent.copy()
    df["lat_bin"] = pd.qcut(df.lat, q=min(20, len(df) // 3 + 1),
                            labels=False, duplicates="drop")
    order = []
    for b in sorted(df.lat_bin.unique()):
        sub = df[df.lat_bin == b].sort_values("lon", ascending=(b % 2 == 0))
        order.extend(sub.fips5.tolist())
    rank = {f: i for i, f in enumerate(order)}
    df["spatial_order"] = df.fips5.map(rank)
    return df.drop(columns="lat_bin").sort_values("spatial_order").reset_index(drop=True)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    keep = panel_fips()
    cent = snake_order(build_centroids(keep))
    adj = build_adjacency(keep)
    cent.to_csv(os.path.join(OUT, "county_centroids.csv"), index=False,
                float_format="%.6f")
    adj.to_csv(os.path.join(OUT, "county_adjacency.csv"), index=False)

    deg = pd.concat([adj.fips5, adj.neighbor_fips5]).value_counts()
    missing = keep - set(cent.fips5)
    print(f"counties in panel: {len(keep)} | with centroid: {len(cent)} "
          f"| missing centroid: {len(missing)}")
    print(f"adjacency edges: {len(adj)} | mean neighbours/county: {deg.mean():.1f}")
    if missing:
        print(f"  no centroid for: {sorted(missing)[:10]}{'...' if len(missing) > 10 else ''}")


if __name__ == "__main__":
    main()

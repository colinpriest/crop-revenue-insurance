# Synthetic-Data Benchmark Schema

Data-prep layer for benchmarking **copula-, deep-learning-, and MICE-based**
tabular generators on **actuarial** fidelity metrics (tail extrapolation,
heterogeneous tail dependence, spatial dependence, downstream rating utility).

Built by `src/enrich_spatial.py` + `src/reshape_benchmark.py` into
`data/benchmark/`. **Independent of** the replication pipeline — nothing here
modifies `data/processed/` or `results/`.

Default downstream target coverage: **90%** (most tail-sensitive).
Primary spatial resolution: **ASD** (crop-reporting district); **county** is the
stress tier.

---

## 1. Unit of independent generation

Tabular generators assume i.i.d. rows. In this data the only approximately
independent replication unit is the **year**: yields are assumed independent
over time (after detrending), but within a year the counties are one
spatially-correlated draw sharing a single national price shock. Two row
definitions therefore serve different metric families:

| Track | File(s) | Row = | Shape | Use for |
|---|---|---|---|---|
| **A — Portfolio** | `panel_wide_{state,asd,county}.csv` | one **year** | 51 × (2 price + K unit residuals) | spatial dependence, heterogeneous tail dependence, portfolio VaR/TVaR, tail extrapolation |
| **B — Conditional** | `panel_long.csv` | one **county-year** | 33,455 × 18 | marginal fidelity, TSTR downstream utility, constraint satisfaction, privacy |

**Track A must be used for any spatial/portfolio-tail metric** — generating
county-years independently (Track B) destroys spatial and price–yield
dependence by construction, so Track B is only valid for marginal/conditional
and downstream-utility metrics.

### Resolution ladder (Track A)

`K` = number of spatial-unit columns; tests how each generator degrades as
exposure granularity grows against fixed `n = 51` years.

| Resolution | K | Regime | Role |
|---|---|---|---|
| `state` | 8 | n ≫ p | sanity tier — every generator should pass |
| `asd` | 71 | p ≈ n | **primary** — copula/MICE/Gaussian-field cope, DL strains |
| `county` | 711 | p ≫ n | **stress** — only structured methods fit |

Columns in every wide file follow a **serpentine spatial order** (`spatial_order`
in `units_{res}.csv`): adjacent columns are geographically near (validated:
mean adjacent-column residual correlation +0.65 vs +0.38 overall), so
order-sensitive generators can exploit locality and a fixed column maps to a
fixed unit.

---

## 2. Spatial reference files ("what is adjacent")

Three redundant, generator-agnostic forms:

| File | Columns | Form |
|---|---|---|
| `county_centroids.csv` | `fips5, state_alpha, county_name, lat, lon, spatial_order` | numeric coordinates — usable by copula/MICE/DL directly |
| `county_adjacency.csv` | `fips5, neighbor_fips5` | shared-border edge list (undirected, canonicalised) — graph-aware methods & spatial-fidelity evaluation |
| `units_{res}.csv` | `unit_id, column, lat, lon, spatial_order, n_counties, …` | column ↔ spatial-unit map for Track A |

Evaluate spatial fidelity of synthetic data with a **variogram / Moran's I on
the residual field** using these coordinates/edges — not by reading any single
precomputed neighbour column (which would leak).

---

## 3. Column taxonomy — three roles

Every column is exactly one of: **deterministic** (derived), **stochastic**
(to be learned), or a **downstream target/predictor**. The benchmark must not
reward a generator for "learning" a deterministic identity, and *should* score
whether synthetic rows satisfy those identities.

### 3a. Deterministic columns (functionally derived)

Exclude from the generative vector; recompute post-hoc, **or** keep and score
as a *constraint-satisfaction* metric (do synthetic rows obey them exactly?).

| Column (file) | Exact identity |
|---|---|
| `yield_trend` (proc.) | `α_c + β_c·(year − 1975)` |
| `yield_resid` / `y_resid_*` | `yield_bu_acre − yield_trend` |
| `yield_ratio` | `yield_bu_acre / yield_trend` |
| `price_harvest` | `price_base · (1 + price_pctchg)` |
| `price_pctchg` | `price_harvest / price_base − 1` |
| `revenue_actual` | `yield_bu_acre · price_harvest` |
| `aph` | `mean_t(yield_bu_acre)` — per-county statistic, not a free variable |
| `guarantee` | `max(price_base, price_harvest) · aph · 0.90` |
| `indemnity_90` | `(1.5 / 0.90) · max(0, guarantee − revenue_actual)` |

**Minimal stochastic core:** everything above collapses to a small free vector.
A generator only needs to model —
* **Track A row:** `price_base`, `price_pctchg`, and the `K` unit residuals
  `y_resid_*`;
* **Track B row:** `price_base`, `price_pctchg`, `yield_resid` (county),
  conditioned on `lat/lon/asd5/year`.
`aph`, trend, revenue, guarantee and indemnity are then re-derived.

### 3b. Stochastic relationships (what generators must learn / metrics score)

| Relationship | Structure | Benchmark axis |
|---|---|---|
| `yield_resid` ↔ `price_pctchg` | **negative, asymmetric lower-tail** (bad yield ↔ price spike); pooled τ ≈ −0.18, **heterogeneous across counties** | heterogeneous tail dependence — score the *spread* of per-unit λ_L, not just the mean |
| `y_resid_i` ↔ `y_resid_j` | spatial, decays with centroid distance; adjacent-unit corr ≈ +0.65 | spatial dependence fidelity (variogram, Moran's I) |
| `price_base_t` ↔ `price_base_{t−1}` | temporal **regime break** (pre-2007 ≈ $2.5 vs post-2007 $4–6) | temporal tail extrapolation |
| `yield_resid` marginal | skew ≈ −1.0, **varies by county** | per-unit left-tail marginal fidelity |

### 3c. Downstream target & predictors (Track B)

For **train-on-synthetic, test-on-real (TSTR)** utility:

* **Target:** `indemnity_90` — the GRIP-HR pure premium / loss cost at 90%
  coverage. (Swap coverage via `TARGET_COV` in `reshape_benchmark.py`;
  alt targets: `revenue_actual`, or loss ratio.)
* **Predictors:** `yield_bu_acre` (or `yield_resid`), `price_base`,
  `price_harvest`, `aph`, `lat`, `lon`, `asd5`, `year` (coverage is fixed at
  0.90 in this build).
* **Metric:** fit a rating model (GLM + GBM) on synthetic `predictors → target`,
  test on real; compare predicted pure premiums and — critically —
  **TVaR/CTE of the indemnity distribution**, not just the mean. Because the
  target is deterministic given predictors, TSTR here really tests whether the
  generator captured the predictor *joint distribution and its tails*.

---

## 4. Tail-extrapolation holdout

Bake in a **temporal** split, not a random one: fit generators on
**1975–2009**, evaluate on **2010–2025** (includes the 2012 systemic drought
and the post-2007 price regime). Report VaR/TVaR of the synthetic **portfolio**
loss (Track A: aggregate `indemnity` across a synthetic year's units) against
realised 2012. `dataset_version` in `data/processed/corn_grip_panel_extended.csv`
and the `year` column support this split directly.

---

## 5. Metric → track map (summary)

| Actuarial metric family | Track | Files |
|---|---|---|
| Marginal fidelity (per-unit yield/price) | B, A | `panel_long.csv`, `panel_wide_*` |
| Heterogeneous tail dependence (λ_L per unit) | A | `panel_wide_asd/county` |
| Spatial dependence (variogram, Moran's I) | A | `panel_wide_*` + `county_centroids`/`county_adjacency` |
| Portfolio tail (VaR/TVaR/CTE) & extrapolation | A | `panel_wide_*`, temporal holdout |
| Downstream utility (TSTR pure premium) | B | `panel_long.csv` |
| Constraint satisfaction / coherence | B | `panel_long.csv` (§3a identities) |
| Privacy (DCR, MIA) — optional, data is public | B | `panel_long.csv` |

---

## 6. File manifest (`data/benchmark/`)

```
county_centroids.csv      centroid lat/lon + serpentine spatial_order per county
county_adjacency.csv      shared-border edge list (undirected)
panel_wide_state.csv      Track A, K=8   (sanity)     + units_state.csv,  trend_params_state.csv
panel_wide_asd.csv        Track A, K=71  (PRIMARY)    + units_asd.csv,    trend_params_asd.csv
panel_wide_county.csv     Track A, K=711 (STRESS)     + units_county.csv, trend_params_county.csv
panel_long.csv            Track B, 33,455 county-years, target = indemnity_90
```

`trend_params_{res}.csv` (`unit_id, resolution, alpha, beta`) lets any synthetic
residual row be re-inflated to a yield: `yield = α + β·(year−1975) + resid`.

Rebuild: `python src/enrich_spatial.py && python src/reshape_benchmark.py`
(needs the Census reference files in `data/raw/spatial/`; see `enrich_spatial.py`).

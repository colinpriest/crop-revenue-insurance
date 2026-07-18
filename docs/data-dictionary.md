# Data Dictionary

Final data products live in `data/processed/`. Raw inputs (`data/raw/`) are
kept for provenance and are reproducible via `src/filter_nass.py`.

## 1. `corn_grip_panel_1975_2009.csv` / `.parquet` — Dataset 1 (replication)

One row per county-year. 21,035 rows = 601 counties × 35 years (1975–2009),
complete balanced panel. County trends fitted on 1975–2009.

| Column | Type | Units | Definition / formula | Source |
|---|---|---|---|---|
| `state_fips` | str(2) | — | State FIPS code | NASS |
| `state_alpha` | str(2) | — | State postal abbreviation (IL, IN, IA, MI, MN, OH, NE, WI) | NASS |
| `state_name` | str | — | State name | NASS |
| `county_fips` | str(3) | — | County ANSI/FIPS code within state | NASS |
| `county_name` | str | — | County name | NASS |
| `asd_code` | int | — | NASS Agricultural Statistics District code | NASS |
| `fips5` | str(5) | — | `state_fips + county_fips` (unique county key) | derived |
| `year` | int | — | Harvest/crop year (NASS marketing-year convention) | NASS |
| `yield_bu_acre` | float | bu/acre | Observed county corn-grain yield (`CORN, GRAIN – YIELD, MEASURED IN BU / ACRE`, survey, county level) | NASS |
| `yield_trend` | float | bu/acre | Fitted county linear trend ŷ = α̂_c + β̂_c·(year − 1975), OLS on 1975–2009 | derived |
| `yield_resid` | float | bu/acre | Detrending option A (levels): `yield_bu_acre − yield_trend` | derived |
| `yield_ratio` | float | ratio | Detrending option B (relative): `yield_bu_acre / yield_trend` | derived |
| `price_base` | float | $/bu | Base (projected) price: February average of December CBOT corn futures settlements | farmdoc/RMA (see below) |
| `price_harvest` | float | $/bu | Harvest price: October average of the same December contract | farmdoc/RMA |
| `price_ratio` | float | ratio | `price_harvest / price_base` | derived |
| `price_pctchg` | float | ratio | `price_ratio − 1` (the paper's price variable) | derived |
| `aph` | float | bu/acre | County APH proxy = mean of `yield_bu_acre` over the panel window (paper: "APH is the mean yield of each county") | derived |
| `revenue` | float | $/acre | `yield_bu_acre × price_harvest` | derived |
| `guarantee_hr_65/75/85/90` | float | $/acre | GRIP-HR revenue guarantee `max(price_base, price_harvest) × aph × cov` for cov = 0.65/0.75/0.85/0.90 | derived |
| `indemnity_hr_65/75/85/90` | float | $/acre | Historical GRIP-HR indemnity `1.5 × max(0, guarantee − revenue)` (leverage 1.5; see note) | derived |
| `dataset_version` | str | — | `"original_window_1975_2009"` | derived |

Note: the panel's `indemnity_hr_*` columns use the spec's literal `1.5 ×
shortfall`. The replication additionally applies the GRIP protection scaling
(1.5/cov — see `docs/replication-specs.md` §1.5), computed on the fly.

## 2. `corn_grip_panel_extended.csv` / `.parquet` — Dataset 2 (extended)

Same structure as Dataset 1 plus the columns below. 33,455 rows, 711
counties, years 1975–2025 (all county-years with a reported yield and an
available price year — no balanced-panel restriction). Trend, APH,
guarantee and indemnity columns are computed from the **full-sample**
(1975–2025) trend and APH.

| Additional column | Definition |
|---|---|
| `yield_trend` / `yield_resid` / `yield_ratio` | trend fitted on 1975–2025 (full window) |
| `yield_trend_7509` / `yield_resid_7509` / `yield_ratio_7509` | trend fitted on 1975–2009 only (NaN for counties absent from Dataset 1); use these to treat post-2009 years as out-of-sample |
| `dataset_version` | `"original_window_1975_2009"` for year ≤ 2009, `"extended_window"` for 2010–2025 |

## 3. `price_summary.csv`

One row per year, 1972–2025.

| Column | Units | Definition |
|---|---|---|
| `year` | — | Crop/insurance year |
| `price_base` | $/bu | February average of December CBOT corn futures (projected price) |
| `price_harvest` | $/bu | October average of December CBOT corn futures (harvest price) |
| `price_ratio` | ratio | harvest / base |
| `price_pctchg` | ratio | harvest/base − 1 |

Sources: 1972–2015 farmdoc daily (Univ. of Illinois) 5 Jan 2016, Table 1;
2016–2018 AFBF Market Intel reviews; 2019–2025 RMA price discovery
(via cropcoverage.com and farmdoc daily harvest-price articles). Values are
the published crop-insurance discovery prices, rounded to $0.01.

## 4. `county_trend_params.csv`

Per county × trend window (two rows per county: `1975_2009` and `1975_2025`).

| Column | Definition |
|---|---|
| `fips5`, `state_fips`, `county_fips`, `state_alpha`, `county_name` | county identifiers |
| `alpha_c` | trend intercept (bu/acre) at t = 0 (1975) |
| `beta_c` | trend slope (bu/acre per year) |
| `n_obs` | observations used in the OLS fit |
| `trend_window` | `1975_2009` or `1975_2025` |

## 5. `aph_table.csv`

One row per Dataset-1 county.

| Column | Definition |
|---|---|
| `fips5` + identifiers | county key |
| `aph_1975_2009` | mean observed yield 1975–2009 (bu/acre) |
| `guarantee_base_65/75/85/90` | baseline guarantee at base price $4: `4 × aph × cov` ($/acre) |

## 6. `data/raw/nass_county_corn_yields.csv`

Filtered NASS bulk-dump extract (33,458 rows): county corn grain yields,
survey estimates, 8 states, 1975–2025. Columns: `state_fips, state_alpha,
state_name, county_fips, county_name, asd_code, year, yield_bu_acre`.
Suppressed/withheld NASS records ("(D)") are dropped; "OTHER (COMBINED)
COUNTIES" pseudo-counties (no ANSI code) are excluded.

## 7. `results/` (replication outputs)

`table1_lossmin_single_freq.csv`, `table2_osll_single_freq.csv`,
`table3_lossmin_mixture_freq.csv`, `table4_lossmin_mixture_weights_*.csv`,
`table5_osll_mixture_freq.csv`, `table6_osll_mixture_weights.csv`,
`table7_rates.csv`, `table7_rmse_vs_optmix.csv`,
`table8_jackknife_significance.csv`, `county_rates.csv` — analogs of the
paper's Tables 1–8 plus per-county rates; produced by
`src/replicate_paper.py`. Rates are $/acre expected GRIP-HR indemnities
(protection-scaled, base price $4).

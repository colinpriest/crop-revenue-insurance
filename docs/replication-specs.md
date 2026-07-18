# Reverse-Engineered Specification of Ghosh, Woodard & Vedenov (2011)

**Paper:** *Efficient Estimation of Copula Mixture Models: An Application to the
Rating of Crop Revenue Insurance*, Ghosh, Woodard & Vedenov, AAEA & NAREA Joint
Annual Meeting, July 2011 ([paper/](../paper/)).

This document records (a) the exact specification we reconstructed from the
paper, (b) every assumption we had to make where the paper is silent or
ambiguous, and (c) differences between the data the paper appears to have used
and the data built under `specs/data-specs.md`.

---

## 1. Reconstructed specification

### 1.1 Data

| Item | Paper | How we reproduce it |
|---|---|---|
| Crop | Corn (grain) | same |
| Geography | 602 counties in IL, IN, IA, MI, MN, OH, NE, WI | 601 counties (see §3.1) |
| Years | 1975–2009 (n = 35 per county; the abstract says "1973–2009" but the Data section and the n = 35 used in the CV/jackknife imply 1975–2009) | 1975–2009 |
| Yield source | USDA NASS county yields | NASS Quick Stats bulk dump (`qs.crops_20260717.txt.gz`), survey county estimates, `CORN, GRAIN – YIELD, MEASURED IN BU / ACRE` |
| Sample rule | not stated (602 counties) | counties with a complete 35-year record 1975–2009 |
| Price variable | percentage change between harvest price and base price | same |
| Base price | average December CBOT corn futures settlement over February | published RMA/farmdoc projected prices (identical definition) |
| Harvest price | average December futures settlement over October | published RMA/farmdoc harvest prices |

### 1.2 Yield detrending

Per county OLS linear trend, homoscedastic errors (paper cites Sherrick et al.
2004):

    y_ct = alpha_c + beta_c * t + e_ct,   t = year - 1975

The paper does not say whether level residuals or ratio residuals are used; we
store both (`yield_resid`, `yield_ratio`) and use **level residuals** for the
dependence (copula) estimation.

### 1.3 Copula estimation (CML)

* Pseudo-observations: ranks/(T+1) of the price % change and of the detrended
  yield residuals.
* **Yield flip:** Gumbel and Clayton admit only positive dependence, and the
  paper states "perfectly negatively correlated yields were generated to allow
  for a positive co dependence between prices and yields." We implement this
  as u_yield → 1 − u_yield before fitting *every* copula (so all six copulas
  see the same, positively-dependent data), flipping back when simulating.
* Six models: Gaussian (MLE for ρ), Student-t (MLE for ρ, ν), Frank, Gumbel,
  Clayton (1-parameter MLE each), and a kernel copula: Gaussian product kernel
  on normal scores with the normal-reference ("rule of thumb") bandwidth
  1.06·σ̂·n^(−1/5) per margin — the paper says "normal kernel and rule of
  thumb for bandwidth selection".

### 1.4 Marginals for simulation (5,000 draws per copula)

* **Price:** lognormal with mean equal to the base price and "variance … the
  price volatility". The base price "is given to be 4". We reconstruct this as
  the 2009 RMA projected price (≈ $4.04–4.13, i.e. "4") and the **2009 RMA
  volatility factor σ = 0.36**. See §2.2 — this value was recovered by
  calibration, and it also matches the paper's rate structure almost exactly.
  Simulated harvest price: H = 4·exp(0.36·Z − 0.36²/2), Z ~ N(0,1) via the
  copula's price uniform.
* **Yield:** "Empirical distribution"; we use interpolated empirical quantiles
  of the county's observed 1975–2009 yields (see §2.3 for why raw rather than
  re-centered detrended yields).

### 1.5 GRIP-HR indemnity

The paper's Eq. (4) is typographically mangled. The pieces
(`Max(BasePrice, HarvestPrice)`, `Ybar`, `HarvestPrice*y`, `/ Cov`, `*1.5`)
are consistent with the actual RMA GRIP-HR payout:

    trigger    = max(B, H) * APH * cov
    protection = 1.5 * max(B, H) * APH          (leverage factor 1.5)
    indemnity  = protection * max(0, trigger − y·H) / trigger
               = (1.5 / cov) * max(0, max(B,H)·APH·cov − y·H)

with B = 4, APH = county mean yield, cov ∈ {0.65, 0.75, 0.85, 0.90}.
The (1.5/cov) scaling — not a bare 1.5 — is required to reproduce the
paper's Table 7 rate pattern (see §2.2).

### 1.6 Out-of-sample objectives (leave-one-out over the 35 years)

For each county and each holdout year i, each copula is re-fitted on the other
34 observations. The holdout's pseudo-observation is its rank in the training
sample: (r + 0.5)/(35) (out-of-sample ECDF — not stated in the paper).

* **OSLL objective:** log copula density at the holdout point, summed over the
  35 holdouts. Single-copula ranking = argmax OSLL (paper Table 2). Mixture
  weights maximize Σᵢ log(w·f_ik + (1−w)·f_il) over w ∈ [0,1] for each of the
  15 pairs (Tables 5, 6).
* **Loss-minimization objective:** the LOO expected indemnity r̂_i,k
  (simulation from the 34-obs fit) versus the "actual indemnity" r_i of the
  holdout year, C_k = Σᵢ (r̂_i,k − r_i)². We compute r_i by valuing year i's
  observed (price change, yield) in the same GRIP formula, with the observed
  price mapped to the $4 scale: p_i = 4·(harvest_i/base_i). (The paper never
  defines r_i precisely.) Mixture weights have the closed-form least-squares
  solution clipped to [0,1] (Tables 1, 3, 4).

### 1.7 Rates and inference

* County rate = mean simulated indemnity from the full-sample (35-obs) copula
  fit, 5,000 draws (Table 7); OptMix = Gumbel–Clayton mixture at the county's
  OSLL-optimal weight.
* Jackknife (Table 8): for copula k vs mixture m, θ̂ = rate_k − rate_m and the
  jackknife variance (n−1)/n · Σᵢ(θ̂₍ᵢ₎ − θ̄)² over the 35 leave-one-out
  estimates; significance = |θ̂|/sd > 1.96.

---

## 2. Assumptions we had to make (paper silent or ambiguous)

1. **Holdout pseudo-observation rule** (§1.6): out-of-sample ECDF
   (r + 0.5)/35. Any reasonable variant changes densities only marginally.
2. **Price volatility σ = 0.36** (§1.4): the paper says the lognormal variance
   is "the price volatility" but never gives the number. The historical std of
   log(harvest/base) over 1975–2009 is **0.165**, which produces rates ~4×
   too small. σ = 0.36 — the actual 2009 RMA corn volatility factor — plus
   the (1.5/cov) GRIP scaling reproduces the paper's Table 7 coverage
   structure almost exactly (65%:90% rate ratio 0.254 vs paper's 0.255).
   `--sigma 0` re-runs everything with the historical estimate.
3. **Yield marginal = raw yields** (§1.4): using detrended yields re-centered
   to the 2009 trend (the "modern" Sherrick-style choice) gives rates several
   times smaller than Table 7 at low coverage; the empirical distribution of
   the *raw* 1975–2009 yields (with APH = raw mean, matching "APH is the mean
   yield of each county") reproduces the paper's levels. This is likely what
   the authors did, even though it mixes trend and shock variability.
4. **Dependence data = detrended residuals**: the paper detrends explicitly,
   and raw-yield ranks would be confounded with the time trend.
5. **Mixture estimation:** the paper plugs optimal weights "back into the
   mixture density"; for rates we exploit that a copula-mixture's expected
   indemnity is the weight-average of component expected indemnities (exact,
   since expectation is linear in the mixing distribution).
6. **OptMix in Table 7** = Gumbel–Clayton (the paper calls it "the best
   optimal mix" under both objectives) at each county's OSLL weight.
7. **Random seeds / simulation error:** 5,000 draws leaves ±1–2% Monte-Carlo
   noise in county rates; the paper does not discuss seeds or common random
   numbers.

---

## 3. Paper's data vs `specs/data-specs.md` — differences found

### 3.1 County count: 602 vs 601

Applying the spec's rule (complete 1975–2009 yield record in the 8 states)
to the 2026 NASS Quick Stats snapshot yields **601** counties, not 602. NASS
has revised/back-filled county estimates since 2011 (and discontinued county
estimates for some small-acreage counties from 2008 onward under its
publication-standards change), so an exact county-set match is not
recoverable. The row count is 21,035 = 601 × 35 (perfectly balanced), versus
the paper's implied 21,070.

### 3.2 Start year: abstract says 1973, data section says 1975

The paper's abstract says "data of corn from 1973-2009"; its Data section says
1975–2009 and the methodology uses n = 35 (⇒ 1975–2009). The specs correctly
adopt 1975–2009 for Dataset 1.

### 3.3 Coverage levels

`specs/data-specs.md` §4.2 lists only Cov ∈ {0.65}; the paper uses
{0.65, 0.75, 0.85, 0.90}. We build guarantee/indemnity columns and run the
replication at **all four** levels.

### 3.4 Indemnity formula

The spec's §4.2 formula collapsed to "Max(0)" (mangled extraction from the
paper's own mangled Eq. 4). We implement the full GRIP-HR formula of §1.5,
including the 1/cov protection scaling that the spec omits.

### 3.5 Price data provenance

The spec asks for daily December-contract futures settlements aggregated to
Feb/Oct means. Free, redistributable daily settlement archives for 1975–2009
do not exist (CME/Barchart data are licensed), so we use the *published*
Feb/Oct averages from farmdoc/RMA (1972–2015: farmdoc daily 5 Jan 2016
Table 1; 2016–2018: AFBF Market Intel; 2019–2025: RMA price discovery as
republished by cropcoverage.com, cross-checked against farmdoc daily). These
are by construction the same quantities the paper describes; rounding is to
cents ($0.01).

### 3.6 Base price / volatility for rating

The spec (§3.1.4) says to compute lognormal parameters from historical sample
moments. The paper instead uses *given* RMA rating parameters (base = 4,
σ = price volatility ≈ 0.36). We default to the paper's values for the
replication and expose `--sigma` for the spec's data-driven alternative.

### 3.7 Dataset 2 price years

Harvest prices exist only through 2025 (the 2026 harvest price is set in
Oct 2026), so the extended panel effectively ends with the 2025 crop year even
though NASS yields for 2025 are complete and the spec mentions "2025 or 2026".

### 3.8 Revenue definition

Spec §4.1 defines Revenue_ct = Y_ct × HarvestPrice_t with "possibly detrended"
yield; we store raw-yield revenue (consistent with GRIP, which settles on
actual county yield × harvest price).

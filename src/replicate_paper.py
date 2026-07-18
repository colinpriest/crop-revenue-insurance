"""Replicate Ghosh, Woodard & Vedenov (2011): copula mixtures for GRIP rating.

Reverse-engineered pipeline (see docs/replication-specs.md for the full
specification and every assumption):

per county (n = 35 years, 1975-2009):
  dependence     copula fitted on (price % change, detrended yield residual);
                 pseudo-obs = ranks/(T+1), yields FLIPPED (1-u) so dependence
                 is positive, as required by Gumbel/Clayton (paper p.13).
  marginals      price ~ lognormal, E[price] = base = $4, sigma = 0.36 (2009
                 RMA corn volatility factor; calibrated - see
                 docs/replication-specs.md); yield ~ empirical distribution of
                 the observed 1975-2009 county yields.
  GRIP-HR        indemnity = (1.5/cov) * max(0, max(4, H)*APH*cov - y*H),
                 cov in {.65,.75,.85,.90}; APH = county mean yield.
  leave-one-out  fit each copula on 34 obs ->
                   (a) log density at the holdout (OSLL objective)
                   (b) expected indemnity via simulation (loss-min objective)
  mixtures       all 15 pairs; OSLL weights maximize sum_i log(w f_ik +
                 (1-w) f_il); loss-min weights minimize sum_i (w EI_ik +
                 (1-w) EI_il - r_i)^2 (closed form, clipped to [0,1]).
  rates          expected indemnity from full-sample fits (Nsim draws);
                 OptMix = Gumbel-Clayton mixture at county OSLL weight.
  jackknife      significance of rate differences between each single copula
                 and the Frank-Clayton / Gumbel-Clayton mixtures.

Outputs -> results/ (analogs of the paper's Tables 1-8).

Usage:
  python src/replicate_paper.py [--nsim 5000] [--max-counties N] [--workers K]
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from copulas import (COPULA_NAMES, ClaytonCopula, FrankCopula, GaussianCopula,
                     GumbelCopula, KernelCopula, StudentTCopula, pseudo_obs)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
RESULTS = os.path.join(ROOT, "results")

BASE_PRICE = 4.0                       # paper: "base price ... is given to be 4"
LEVERAGE = 1.5
COVERAGES = np.array([0.65, 0.75, 0.85, 0.90])
PAIRS = list(itertools.combinations(range(6), 2))   # 15 mixtures
PAIR_NAMES = [f"{COPULA_NAMES[a]}-{COPULA_NAMES[b]}" for a, b in PAIRS]

_CLS = [KernelCopula, GaussianCopula, StudentTCopula,
        FrankCopula, GumbelCopula, ClaytonCopula]


# ------------------------------------------------------------------ marginals
def price_from_u(u, sigma):
    """Lognormal price quantile with mean BASE_PRICE."""
    z = stats.norm.ppf(np.clip(u, 1e-9, 1 - 1e-9))
    return BASE_PRICE * np.exp(sigma * z - 0.5 * sigma * sigma)


def yield_from_u(u, sample):
    """Empirical (interpolated) quantile of the county yield sample."""
    return np.quantile(sample, np.clip(u, 0, 1), method="linear")


def indemnity(price, yld, aph):
    """GRIP-HR indemnity per acre for each coverage level -> (4, n).

    Actual GRIP payout: protection (LEVERAGE x expected revenue) times the
    revenue shortfall as a share of the trigger, i.e.
        1.5 * maxP*APH * max(0, cov*maxP*APH - y*H) / (cov*maxP*APH)
      = (1.5/cov) * max(0, guarantee - revenue).
    The 1/cov factor is the "/ Cov" term in the paper's garbled Eq. (4); this
    scaling (with sigma=0.36) reproduces the paper's Table 7 rate structure.
    """
    guar = np.maximum(BASE_PRICE, price)[None, :] * aph * COVERAGES[:, None]
    short = np.maximum(0.0, guar - (yld * price)[None, :])
    return LEVERAGE / COVERAGES[:, None] * short


def ecdf_holdout(train, x):
    """Out-of-sample ECDF value of x given the training sample."""
    return (np.searchsorted(np.sort(train), x, side="right") + 0.5) / (len(train) + 1.0)


# ------------------------------------------------------------ mixture weights
def osll_weight(f1, f2):
    """argmax_w sum log(w f1 + (1-w) f2); returns (w, osll)."""
    def neg(w):
        return -np.log(np.maximum(w * f1 + (1 - w) * f2, 1e-300)).sum()
    res = optimize.minimize_scalar(neg, bounds=(0.0, 1.0), method="bounded")
    return float(res.x), -float(res.fun)


def lossmin_weight(e1, e2, r):
    """argmin_w sum (w e1 + (1-w) e2 - r)^2, closed form clipped to [0,1]."""
    d = e1 - e2
    denom = (d * d).sum()
    w = float(((r - e2) * d).sum() / denom) if denom > 1e-12 else 0.5
    w = min(max(w, 0.0), 1.0)
    loss = float(((w * e1 + (1 - w) * e2 - r) ** 2).sum())
    return w, loss


# ------------------------------------------------------------- county worker
def process_county(args):
    """fips, yields (raw, marginal), resid (detrended, dependence), pct, sigma, nsim."""
    fips, yields, resid, pct, sigma, nsim = args
    T = len(yields)
    base_seed = int.from_bytes(fips.encode(), "little") % (2 ** 31)

    def sim_rng(k):
        # common random numbers per (county, copula): identical draws across
        # the full-sample fit and all 35 LOO fits, so jackknife deviations
        # reflect parameter changes rather than Monte-Carlo noise
        return np.random.default_rng(base_seed * 64 + k)

    aph = float(np.mean(yields))
    up = pseudo_obs(pct)
    uyf = 1.0 - pseudo_obs(resid)           # flipped yields: positive dependence

    # observed prices on the $4 scale and actual per-year indemnities (4, T)
    p_obs = BASE_PRICE * (1.0 + pct)
    r_actual = indemnity(p_obs, yields, aph)

    # ---------------- full-sample fits, simulated rates per copula (6, 4)
    rates = np.zeros((6, 4))
    for k, cls in enumerate(_CLS):
        cop = cls().fit(up, uyf)
        su, svf = cop.sample(nsim, sim_rng(k))
        H = price_from_u(su, sigma)
        Y = yield_from_u(1.0 - svf, yields)
        rates[k] = indemnity(H, Y, aph).mean(axis=1)

    # ---------------- leave-one-out
    dens = np.zeros((T, 6))                  # copula density at holdout
    ei = np.zeros((T, 6, 4))                 # LOO expected indemnity
    for i in range(T):
        mask = np.ones(T, bool)
        mask[i] = False
        p_tr, y_tr, res_tr = pct[mask], yields[mask], resid[mask]
        u_tr = pseudo_obs(p_tr)
        vf_tr = 1.0 - pseudo_obs(res_tr)
        u_i = ecdf_holdout(p_tr, pct[i])
        vf_i = 1.0 - ecdf_holdout(res_tr, resid[i])
        for k, cls in enumerate(_CLS):
            cop = cls().fit(u_tr, vf_tr)
            dens[i, k] = np.exp(float(cop.logpdf(np.array([u_i]),
                                                 np.array([vf_i]))[0]))
            su, svf = cop.sample(nsim, sim_rng(k))
            H = price_from_u(su, sigma)
            Y = yield_from_u(1.0 - svf, y_tr)
            ei[i, k] = indemnity(H, Y, float(np.mean(y_tr))).mean(axis=1)

    # ---------------- OSLL objective
    osll_single = np.log(np.maximum(dens, 1e-300)).sum(axis=0)      # (6,)
    osll_mix_w = np.zeros(15)
    osll_mix_ll = np.zeros(15)
    for j, (a, b) in enumerate(PAIRS):
        osll_mix_w[j], osll_mix_ll[j] = osll_weight(dens[:, a], dens[:, b])

    # ---------------- loss-minimization objective (per coverage)
    loss_single = np.zeros((4, 6))
    loss_mix_w = np.zeros((4, 15))
    loss_mix = np.zeros((4, 15))
    for c in range(4):
        loss_single[c] = ((ei[:, :, c] - r_actual[c][:, None]) ** 2).sum(axis=0)
        for j, (a, b) in enumerate(PAIRS):
            loss_mix_w[c, j], loss_mix[c, j] = lossmin_weight(
                ei[:, a, c], ei[:, b, c], r_actual[c])

    # ---------------- OptMix rate: Gumbel-Clayton at the county OSLL weight
    j_gc = PAIR_NAMES.index("Gumbel-Clayton")
    w_gc = osll_mix_w[j_gc]
    rate_optmix = w_gc * rates[4] + (1 - w_gc) * rates[5]           # (4,)

    # ---------------- jackknife significance vs the two reference mixtures
    # LOO mixture expected indemnities at the county-level optimal weights
    j_fc = PAIR_NAMES.index("Frank-Clayton")
    w_fc = osll_mix_w[j_fc]
    ei_fc = w_fc * ei[:, 3, :] + (1 - w_fc) * ei[:, 5, :]           # (T, 4)
    ei_gc = w_gc * ei[:, 4, :] + (1 - w_gc) * ei[:, 5, :]
    rate_fc = w_fc * rates[3] + (1 - w_fc) * rates[5]
    sig = np.zeros((2, 6, 4), bool)
    for m, (ei_m, rate_m) in enumerate([(ei_fc, rate_fc), (ei_gc, rate_optmix)]):
        for k in range(6):
            theta_i = ei[:, k, :] - ei_m                            # (T, 4)
            var = (T - 1) / T * ((theta_i - theta_i.mean(axis=0)) ** 2).sum(axis=0)
            sd = np.sqrt(np.maximum(var, 1e-300))
            sig[m, k] = np.abs(rates[k] - rate_m) / sd > 1.96

    return dict(fips=fips, aph=aph, rates=rates, rate_optmix=rate_optmix,
                osll_single=osll_single, osll_mix_w=osll_mix_w,
                osll_mix_ll=osll_mix_ll, loss_single=loss_single,
                loss_mix_w=loss_mix_w, loss_mix=loss_mix, sig=sig)


# ------------------------------------------------------------------ reporting
def aggregate(res: list[dict]) -> None:
    os.makedirs(RESULTS, exist_ok=True)
    n = len(res)
    cov_lbl = [f"{int(c*100)}%" for c in COVERAGES]

    # Table 1 analog: loss-min, frequency single copula best, by coverage
    t1 = pd.DataFrame(0.0, index=COPULA_NAMES, columns=cov_lbl)
    for r in res:
        for c in range(4):
            t1.iloc[int(np.argmin(r["loss_single"][c])), c] += 1
    (t1 / n).round(4).to_csv(os.path.join(RESULTS, "table1_lossmin_single_freq.csv"))

    # Table 2 analog: OSLL, frequency single copula best
    t2 = pd.Series(0.0, index=COPULA_NAMES)
    for r in res:
        t2.iloc[int(np.argmax(r["osll_single"]))] += 1
    (t2 / n).round(4).to_csv(os.path.join(RESULTS, "table2_osll_single_freq.csv"),
                             header=["freq_best"])

    # Table 3 analog: loss-min, frequency mixture best, by coverage
    t3 = pd.DataFrame(0.0, index=PAIR_NAMES, columns=cov_lbl)
    for r in res:
        for c in range(4):
            t3.iloc[int(np.argmin(r["loss_mix"][c])), c] += 1
    (t3 / n).round(4).to_csv(os.path.join(RESULTS, "table3_lossmin_mixture_freq.csv"))

    # Table 4 analog: loss-min, average optimal weights (per coverage)
    for c, lbl in enumerate(cov_lbl):
        t4 = pd.Series(np.mean([r["loss_mix_w"][c] for r in res], axis=0),
                       index=PAIR_NAMES)
        t4.round(4).to_csv(os.path.join(
            RESULTS, f"table4_lossmin_mixture_weights_{lbl.strip('%')}.csv"),
            header=["avg_weight_first_component"])

    # Table 5 analog: OSLL, frequency mixture best
    t5 = pd.Series(0.0, index=PAIR_NAMES)
    for r in res:
        t5.iloc[int(np.argmax(r["osll_mix_ll"]))] += 1
    (t5 / n).round(4).to_csv(os.path.join(RESULTS, "table5_osll_mixture_freq.csv"),
                             header=["freq_best"])

    # Table 6 analog: OSLL, average optimal weights
    t6 = pd.Series(np.mean([r["osll_mix_w"] for r in res], axis=0), index=PAIR_NAMES)
    t6.round(4).to_csv(os.path.join(RESULTS, "table6_osll_mixture_weights.csv"),
                       header=["avg_weight_first_component"])

    # Table 7 analog: average rates + RMSE relative to OptMix
    rates = np.array([r["rates"] for r in res])           # (n, 6, 4)
    opt = np.array([r["rate_optmix"] for r in res])       # (n, 4)
    t7 = pd.DataFrame(rates.mean(axis=0).T, index=cov_lbl, columns=COPULA_NAMES)
    t7["OptMix"] = opt.mean(axis=0)
    t7.round(2).to_csv(os.path.join(RESULTS, "table7_rates.csv"))
    rmse = np.sqrt(((rates - opt[:, None, :]) ** 2).mean(axis=0))
    t7b = pd.DataFrame(rmse.T, index=cov_lbl, columns=COPULA_NAMES)
    t7b.round(2).to_csv(os.path.join(RESULTS, "table7_rmse_vs_optmix.csv"))

    # Table 8 analog: jackknife significance frequencies
    sig = np.array([r["sig"] for r in res])               # (n, 2, 6, 4)
    rows = []
    for c, lbl in enumerate(cov_lbl):
        for k, nm in enumerate(COPULA_NAMES):
            rows.append([lbl, nm, sig[:, 0, k, c].mean(), sig[:, 1, k, c].mean()])
    pd.DataFrame(rows, columns=["coverage", "copula", "vs_Frank-Clayton",
                                "vs_Gumbel-Clayton"]).round(4).to_csv(
        os.path.join(RESULTS, "table8_jackknife_significance.csv"), index=False)

    # raw per-county rates
    rec = []
    for r in res:
        row = {"fips5": r["fips"], "aph": r["aph"]}
        for k, nm in enumerate(COPULA_NAMES):
            for c, lbl in enumerate(cov_lbl):
                row[f"rate_{nm}_{lbl.strip('%')}"] = r["rates"][k, c]
        for c, lbl in enumerate(cov_lbl):
            row[f"rate_OptMix_{lbl.strip('%')}"] = r["rate_optmix"][c]
        rec.append(row)
    pd.DataFrame(rec).to_csv(os.path.join(RESULTS, "county_rates.csv"),
                             index=False, float_format="%.4f")
    print(f"aggregated {n} counties -> {RESULTS}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nsim", type=int, default=5000)
    ap.add_argument("--max-counties", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--sigma", type=float, default=0.36,
                    help="lognormal price volatility; 0.36 = 2009 RMA corn "
                         "volatility factor (calibrated to the paper). Pass 0 "
                         "to use the historical std of log(harvest/base).")
    args = ap.parse_args()

    panel = pd.read_csv(os.path.join(PROC, "corn_grip_panel_1975_2009.csv"),
                        dtype={"fips5": str})
    prices = panel[["year", "price_pctchg"]].drop_duplicates().sort_values("year")
    sigma = args.sigma or float(np.log1p(prices.price_pctchg).std(ddof=1))
    print(f"price sigma: {sigma:.4f}")

    tasks = []
    for fips, g in panel.sort_values("year").groupby("fips5"):
        tasks.append((fips, g.yield_bu_acre.to_numpy(float),
                      g.yield_resid.to_numpy(float),
                      g.price_pctchg.to_numpy(float), sigma, args.nsim))
    if args.max_counties:
        tasks = tasks[: args.max_counties]
    print(f"{len(tasks)} counties, nsim={args.nsim}, workers={args.workers}")

    t0 = time.time()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            res = []
            for i, r in enumerate(ex.map(process_county, tasks, chunksize=4)):
                res.append(r)
                if (i + 1) % 25 == 0:
                    el = time.time() - t0
                    print(f"  {i+1}/{len(tasks)} counties  "
                          f"({el:.0f}s, {el/(i+1):.1f}s/county)", flush=True)
    else:
        res = [process_county(t) for t in tasks]
    print(f"done in {time.time()-t0:.0f}s")
    aggregate(res)


if __name__ == "__main__":
    main()

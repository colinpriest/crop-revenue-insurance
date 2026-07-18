"""Bivariate copulas used in Ghosh, Woodard & Vedenov (2011).

Six models: Gaussian, Student-t, Frank, Gumbel, Clayton and a non-parametric
(Gaussian-)kernel copula.  Each exposes

    fit(u, v)          -> fitted params (CML: inputs are pseudo-observations)
    logpdf(u, v)       -> log copula density at points (vectorised)
    sample(n, rng)     -> n draws of (u, v)

Conventions
-----------
* Pseudo-observations are ranks/(T+1) (canonical maximum likelihood).
* Gumbel and Clayton only allow positive dependence.  As in the paper, the
  caller passes *flipped* yield uniforms (1 - u_yield) so that the
  price-change/yield dependence is positive for every copula; flip back after
  simulation.
* The kernel copula uses a Gaussian product kernel on normal scores with
  Silverman's rule-of-thumb bandwidth ("normal kernel and rule of thumb for
  bandwidth selection" in the paper).
"""
from __future__ import annotations

import numpy as np
from scipy import optimize, stats

EPS = 1e-9


def pseudo_obs(x: np.ndarray) -> np.ndarray:
    """Empirical-CDF transform: ranks/(T+1)."""
    r = stats.rankdata(x, method="average")
    return r / (len(x) + 1.0)


def _clip(u):
    return np.clip(np.asarray(u, float), EPS, 1 - EPS)


# --------------------------------------------------------------------------- #
class GaussianCopula:
    name = "Gaussian"

    def __init__(self, rho: float = 0.0):
        self.rho = rho

    def fit(self, u, v):
        u, v = _clip(u), _clip(v)
        x, y = stats.norm.ppf(u), stats.norm.ppf(v)

        def nll(r):
            return -self._logpdf_scores(x, y, r).sum()

        res = optimize.minimize_scalar(nll, bounds=(-0.99, 0.99), method="bounded")
        self.rho = float(res.x)
        return self

    @staticmethod
    def _logpdf_scores(x, y, r):
        r2 = r * r
        return (-0.5 * np.log(1 - r2)
                - (r2 * (x * x + y * y) - 2 * r * x * y) / (2 * (1 - r2)))

    def logpdf(self, u, v):
        x, y = stats.norm.ppf(_clip(u)), stats.norm.ppf(_clip(v))
        return self._logpdf_scores(x, y, self.rho)

    def sample(self, n, rng):
        z1 = rng.standard_normal(n)
        z2 = self.rho * z1 + np.sqrt(1 - self.rho ** 2) * rng.standard_normal(n)
        return stats.norm.cdf(z1), stats.norm.cdf(z2)


# --------------------------------------------------------------------------- #
class StudentTCopula:
    name = "t"

    def __init__(self, rho: float = 0.0, nu: float = 8.0):
        self.rho, self.nu = rho, nu

    def fit(self, u, v):
        u, v = _clip(u), _clip(v)

        def nll(p):
            rho = np.tanh(p[0])
            nu = 2.0 + np.exp(p[1])
            return -self._ll(u, v, rho, nu)

        start = np.array([np.arctanh(np.clip(np.corrcoef(u, v)[0, 1], -0.9, 0.9)),
                          np.log(8.0 - 2.0)])
        res = optimize.minimize(nll, start, method="Nelder-Mead",
                                options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 400})
        self.rho = float(np.tanh(res.x[0]))
        self.nu = float(2.0 + np.exp(res.x[1]))
        return self

    @staticmethod
    def _logpdf_scores(x, y, rho, nu):
        r2 = rho * rho
        quad = (x * x - 2 * rho * x * y + y * y) / (nu * (1 - r2))
        from scipy.special import gammaln
        c = (gammaln((nu + 2) / 2) + gammaln(nu / 2)
             - 2 * gammaln((nu + 1) / 2) - 0.5 * np.log(1 - r2))
        num = -(nu + 2) / 2 * np.log1p(quad)
        den = -(nu + 1) / 2 * (np.log1p(x * x / nu) + np.log1p(y * y / nu))
        return c + num - den

    @classmethod
    def _ll(cls, u, v, rho, nu):
        x, y = stats.t.ppf(u, nu), stats.t.ppf(v, nu)
        return cls._logpdf_scores(x, y, rho, nu).sum()

    def logpdf(self, u, v):
        x = stats.t.ppf(_clip(u), self.nu)
        y = stats.t.ppf(_clip(v), self.nu)
        return self._logpdf_scores(x, y, self.rho, self.nu)

    def sample(self, n, rng):
        z1 = rng.standard_normal(n)
        z2 = self.rho * z1 + np.sqrt(1 - self.rho ** 2) * rng.standard_normal(n)
        w = self.nu / rng.chisquare(self.nu, n)
        x, y = z1 * np.sqrt(w), z2 * np.sqrt(w)
        return stats.t.cdf(x, self.nu), stats.t.cdf(y, self.nu)


# --------------------------------------------------------------------------- #
class FrankCopula:
    name = "Frank"

    def __init__(self, theta: float = 1.0):
        self.theta = theta

    def fit(self, u, v):
        u, v = _clip(u), _clip(v)

        def nll(t):
            if abs(t) < 1e-4:
                return 0.0
            return -self._logpdf_t(u, v, t).sum()

        res = optimize.minimize_scalar(nll, bounds=(-35, 35), method="bounded")
        self.theta = float(res.x)
        return self

    @staticmethod
    def _logpdf_t(u, v, t):
        # c(u,v) = t(1-e^{-t}) e^{-t(u+v)} / [(1-e^{-t}) - (1-e^{-tu})(1-e^{-tv})]^2
        em1 = -np.expm1(-t)                       # 1 - e^{-t}
        eu = -np.expm1(-t * u)
        ev = -np.expm1(-t * v)
        den = em1 - eu * ev
        return (np.log(np.abs(t) + EPS) + np.log(np.abs(em1))
                - t * (u + v) - 2 * np.log(np.abs(den) + EPS)
                + (0.0 if t > 0 else 0.0))

    def logpdf(self, u, v):
        t = self.theta
        if abs(t) < 1e-4:
            return np.zeros_like(_clip(u))
        return self._logpdf_t(_clip(u), _clip(v), t)

    def sample(self, n, rng):
        t = self.theta
        u = rng.uniform(size=n)
        w = rng.uniform(size=n)
        if abs(t) < 1e-4:
            return u, w
        # conditional inversion: solve dC/du = w for v, giving
        # v = -(1/t) ln[1 + w(e^{-t}-1) / (e^{-tu} - w(e^{-tu}-1))]
        etu = np.exp(-t * u)
        v = -1.0 / t * np.log1p(w * np.expm1(-t) / (etu - w * (etu - 1.0)))
        return u, np.clip(v, EPS, 1 - EPS)


# --------------------------------------------------------------------------- #
class ClaytonCopula:
    name = "Clayton"

    def __init__(self, theta: float = 1.0):
        self.theta = theta

    def fit(self, u, v):
        u, v = _clip(u), _clip(v)

        def nll(t):
            return -self._logpdf_t(u, v, t).sum()

        res = optimize.minimize_scalar(nll, bounds=(1e-3, 30), method="bounded")
        self.theta = float(res.x)
        return self

    @staticmethod
    def _logpdf_t(u, v, t):
        # c = (1+t) (uv)^{-(1+t)} (u^{-t} + v^{-t} - 1)^{-(2 + 1/t)}
        s = u ** (-t) + v ** (-t) - 1.0
        s = np.maximum(s, EPS)
        return (np.log1p(t) - (1 + t) * (np.log(u) + np.log(v))
                - (2 + 1 / t) * np.log(s))

    def logpdf(self, u, v):
        return self._logpdf_t(_clip(u), _clip(v), self.theta)

    def sample(self, n, rng):
        # Marshall-Olkin: gamma(1/theta) frailty
        t = self.theta
        g = rng.gamma(1.0 / t, 1.0, n)
        e1, e2 = rng.exponential(size=n), rng.exponential(size=n)
        u = (1 + e1 / g) ** (-1 / t)
        v = (1 + e2 / g) ** (-1 / t)
        return u, v


# --------------------------------------------------------------------------- #
class GumbelCopula:
    name = "Gumbel"

    def __init__(self, theta: float = 1.5):
        self.theta = theta

    def fit(self, u, v):
        u, v = _clip(u), _clip(v)

        def nll(t):
            return -self._logpdf_t(u, v, t).sum()

        res = optimize.minimize_scalar(nll, bounds=(1.0 + 1e-6, 30), method="bounded")
        self.theta = float(res.x)
        return self

    @staticmethod
    def _logpdf_t(u, v, t):
        lu, lv = -np.log(u), -np.log(v)
        A = lu ** t + lv ** t
        At = A ** (1 / t)
        # log C(u,v) = -At ;  c = C(u,v) (uv)^{-1} A^{2/t - 2} (lu lv)^{t-1} (1 + (t-1) A^{-1/t})
        return (-At - np.log(u) - np.log(v)
                + (2 / t - 2) * np.log(A)
                + (t - 1) * (np.log(lu) + np.log(lv))
                + np.log1p((t - 1) / At))

    def logpdf(self, u, v):
        return self._logpdf_t(_clip(u), _clip(v), self.theta)

    def sample(self, n, rng):
        # Marshall-Olkin with positive stable frailty, alpha = 1/theta
        t = self.theta
        a = 1.0 / t
        # Chambers-Mallows-Stuck positive stable
        th = rng.uniform(0, np.pi, n)
        w = rng.exponential(size=n)
        s = (np.sin(a * th) / np.sin(th) ** (1 / a)
             * (np.sin((1 - a) * th) / w) ** ((1 - a) / a))
        e1, e2 = rng.exponential(size=n), rng.exponential(size=n)
        u = np.exp(-((e1 / s) ** a))
        v = np.exp(-((e2 / s) ** a))
        return np.clip(u, EPS, 1 - EPS), np.clip(v, EPS, 1 - EPS)


# --------------------------------------------------------------------------- #
class KernelCopula:
    """Gaussian kernel copula on normal scores, Silverman rule-of-thumb."""
    name = "Kernel"

    def __init__(self):
        self.zx = self.zy = None
        self.h = None

    def fit(self, u, v):
        self.zx = stats.norm.ppf(_clip(u))
        self.zy = stats.norm.ppf(_clip(v))
        n = len(self.zx)
        # Silverman / normal-reference rule of thumb per margin
        self.hx = 1.06 * np.std(self.zx, ddof=1) * n ** (-0.2)
        self.hy = 1.06 * np.std(self.zy, ddof=1) * n ** (-0.2)
        self.hx = max(self.hx, 1e-3)
        self.hy = max(self.hy, 1e-3)
        return self

    def logpdf(self, u, v):
        u, v = _clip(u), _clip(v)
        x, y = stats.norm.ppf(u), stats.norm.ppf(v)
        x = np.atleast_1d(x)[:, None]
        y = np.atleast_1d(y)[:, None]
        kx = stats.norm.pdf((x - self.zx[None, :]) / self.hx) / self.hx
        ky = stats.norm.pdf((y - self.zy[None, :]) / self.hy) / self.hy
        f = (kx * ky).mean(axis=1)
        # copula density = joint density of scores / product of standard normals
        mx = stats.norm.pdf(x[:, 0])
        my = stats.norm.pdf(y[:, 0])
        return np.log(np.maximum(f, 1e-300)) - np.log(mx) - np.log(my)

    def sample(self, n, rng):
        idx = rng.integers(0, len(self.zx), n)
        x = self.zx[idx] + self.hx * rng.standard_normal(n)
        y = self.zy[idx] + self.hy * rng.standard_normal(n)
        return stats.norm.cdf(x), stats.norm.cdf(y)


COPULA_CLASSES = [KernelCopula, GaussianCopula, StudentTCopula,
                  FrankCopula, GumbelCopula, ClaytonCopula]
COPULA_NAMES = [c.name for c in COPULA_CLASSES]


def make(name: str):
    return {c.name: c for c in COPULA_CLASSES}[name]()

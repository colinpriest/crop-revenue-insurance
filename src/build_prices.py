"""Build the corn base/harvest price series (specs/data-specs.md section 3).

Definitions (identical to the paper and to RMA crop-insurance practice in the
Midwest):
  base price     = average daily settlement price of the December CBOT corn
                   futures contract over February of the insurance year
                   (RMA/farmdoc "projected price")
  harvest price  = average daily settlement price of the same December
                   contract over October of the same year

Sources of the numbers embedded below (daily futures settlement archives for
1975-2009 are not freely redistributable, so we use the published Feb/Oct
averages, which are byte-identical to what the paper describes):
  1972-2015: farmdoc daily (Univ. of Illinois), "Possible 2016 Harvest Prices
             for Corn", 5 Jan 2016, Table 1 (fdd010516_tab1.jpg, saved in
             data/raw/).
  2016-2018: American Farm Bureau "Reviewing 2017/2018 Crop Insurance Prices";
             cross-checked with farmdoc daily articles.
  2019-2025: RMA price discovery values as republished by Williamson Crop
             Insurance (cropcoverage.com/prices, OH/IN corn) and farmdoc daily
             harvest-price articles (2023-2025).

Output: data/processed/price_summary.csv with
  year, price_base, price_harvest, price_ratio, price_pctchg
"""
from __future__ import annotations

import os

import pandas as pd

# year: (base/projected price $/bu, harvest price $/bu)
PRICES: dict[int, tuple[float, float]] = {
    1972: (1.24, 1.35), 1973: (1.39, 2.46), 1974: (2.91, 3.80),
    1975: (2.70, 2.90), 1976: (2.72, 2.65), 1977: (2.73, 2.09),
    1978: (2.27, 2.31), 1979: (2.59, 2.78), 1980: (3.12, 3.61),
    1981: (3.76, 2.91), 1982: (3.00, 2.20), 1983: (2.88, 3.48),
    1984: (2.86, 2.78), 1985: (2.66, 2.23), 1986: (2.10, 1.69),
    1987: (1.69, 1.83), 1988: (2.17, 2.89), 1989: (2.71, 2.39),
    1990: (2.47, 2.30), 1991: (2.59, 2.51), 1992: (2.70, 2.09),
    1993: (2.40, 2.49), 1994: (2.68, 2.16), 1995: (2.57, 3.23),
    1996: (3.08, 2.84), 1997: (2.73, 2.81), 1998: (2.84, 2.19),
    1999: (2.40, 2.01), 2000: (2.51, 2.04), 2001: (2.46, 2.08),
    2002: (2.32, 2.52), 2003: (2.42, 2.26), 2004: (2.83, 2.05),
    2005: (2.32, 2.02), 2006: (2.50, 3.03), 2007: (4.06, 3.58),
    2008: (5.40, 4.13), 2009: (4.13, 3.72), 2010: (3.99, 5.46),
    2011: (6.01, 6.32), 2012: (5.68, 7.50), 2013: (5.65, 4.39),
    2014: (4.62, 3.49), 2015: (4.15, 3.83), 2016: (3.86, 3.49),
    2017: (3.96, 3.49), 2018: (3.96, 3.68), 2019: (4.00, 3.90),
    2020: (3.88, 3.99), 2021: (4.58, 5.37), 2022: (5.90, 6.86),
    2023: (5.91, 4.88), 2024: (4.66, 4.16), 2025: (4.70, 4.22),
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "data", "processed", "price_summary.csv")


def build() -> pd.DataFrame:
    df = pd.DataFrame(
        [(y, b, h) for y, (b, h) in sorted(PRICES.items())],
        columns=["year", "price_base", "price_harvest"],
    )
    df["price_ratio"] = df["price_harvest"] / df["price_base"]
    df["price_pctchg"] = df["price_ratio"] - 1.0
    return df


def main() -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df = build()
    df.to_csv(OUT_PATH, index=False, float_format="%.6f")
    print(f"wrote {len(df)} years ({df.year.min()}-{df.year.max()}) -> {OUT_PATH}")


if __name__ == "__main__":
    main()

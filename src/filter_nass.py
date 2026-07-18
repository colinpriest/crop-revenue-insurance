"""Extract county-level corn grain yields from the USDA NASS Quick Stats bulk dump.

Input : data/raw/qs.crops_YYYYMMDD.txt.gz  (tab-delimited, from
        https://www.nass.usda.gov/datasets/)
Output: data/raw/nass_county_corn_yields.csv

Filters (per specs/data-specs.md section 2):
  - SOURCE_DESC        = SURVEY  (annual county estimates, not census)
  - SHORT_DESC         = "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE"
  - AGG_LEVEL_DESC     = COUNTY
  - STATE_ALPHA        in the 8 Midwest states used by the paper
  - DOMAIN_DESC        = TOTAL
  - YEAR              >= 1975
  - COUNTY_ANSI non-empty (drops "OTHER (COMBINED) COUNTIES" pseudo-records,
    which carry county codes 998/999 and no ANSI code)
  - VALUE numeric (drops "(D)" withheld / suppressed records)
"""
from __future__ import annotations

import csv
import glob
import gzip
import os
import sys

STATES = {"IL", "IN", "IA", "MI", "MN", "OH", "NE", "WI"}
SHORT_DESC = "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE"
MIN_YEAR = 1975

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "data", "raw", "nass_county_corn_yields.csv")


def find_dump() -> str:
    hits = sorted(glob.glob(os.path.join(ROOT, "data", "raw", "qs.crops_*.txt.gz")))
    if not hits:
        sys.exit("No qs.crops_*.txt.gz found in data/raw — download it from "
                 "https://www.nass.usda.gov/datasets/ first.")
    return hits[-1]


def main() -> None:
    src = find_dump()
    n_in = n_out = n_suppressed = 0
    with gzip.open(src, "rt", encoding="utf-8", errors="replace", newline="") as fin, \
            open(OUT_PATH, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin, delimiter="\t")
        writer = csv.writer(fout)
        writer.writerow(["state_fips", "state_alpha", "state_name", "county_fips",
                         "county_name", "asd_code", "year", "yield_bu_acre"])
        for row in reader:
            n_in += 1
            if row["SHORT_DESC"] != SHORT_DESC:
                continue
            if row["SOURCE_DESC"] != "SURVEY" or row["AGG_LEVEL_DESC"] != "COUNTY":
                continue
            if row["STATE_ALPHA"] not in STATES or row["DOMAIN_DESC"] != "TOTAL":
                continue
            year = int(row["YEAR"])
            if year < MIN_YEAR:
                continue
            if not row["COUNTY_ANSI"].strip():
                continue
            value = row["VALUE"].strip().replace(",", "")
            try:
                y = float(value)
            except ValueError:
                n_suppressed += 1          # "(D)" etc.
                continue
            writer.writerow([row["STATE_FIPS_CODE"], row["STATE_ALPHA"],
                             row["STATE_NAME"].title(), row["COUNTY_ANSI"],
                             row["COUNTY_NAME"].title(), row["ASD_CODE"], year, y])
            n_out += 1
    print(f"scanned {n_in:,} rows -> kept {n_out:,} county-year yields "
          f"({n_suppressed} suppressed dropped) -> {OUT_PATH}")


if __name__ == "__main__":
    main()

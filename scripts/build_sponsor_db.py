"""
Import a country's public sponsor data into data/regions/<country>.db.

  United States — DOL H-1B (LCA) disclosure files (.xlsx or .csv):
      https://www.dol.gov/agencies/eta/foreign-labor/performance
      python scripts/build_sponsor_db.py --country US LCA_Disclosure_Data_FY2025_Q4.xlsx ...

  United Kingdom — Home Office Register of Licensed Sponsors (.csv):
      https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers
      python scripts/build_sponsor_db.py --country GB Worker_and_Temporary_Worker.csv

Rebuilds the country's database from scratch each run.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from regions import get_region, is_supported  # noqa: E402
from regions.base import DataRegion  # noqa: E402


def build(country: str, paths: list, out: str = None) -> int:
    if not is_supported(country):
        raise SystemExit(f"Unknown country code: {country}")
    region = get_region(country)
    if not isinstance(region, DataRegion):
        raise SystemExit(f"{region.name} has no importable sponsor data yet")
    out = out or region.path
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    total = region.build(paths, tmp)
    os.replace(tmp, out)   # atomic swap — the running app never sees a half-built DB
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="data files (.xlsx or .csv)")
    ap.add_argument("--country", default="US", help="country code: US or GB (default US)")
    ap.add_argument("--out", help="output SQLite path (default data/regions/<country>.db)")
    args = ap.parse_args()
    total = build(args.country, args.files, args.out)
    print(f"\n  Done — {total:,} rows imported for {get_region(args.country).name}")


if __name__ == "__main__":
    main()

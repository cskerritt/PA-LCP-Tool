"""Refresh the VA Reasonable Charges data the tool prices from.

Usage:
  # ingest the official outpatient/professional workbook you downloaded
  python scripts/fetch_va_charges.py --outpatient ~/Downloads/va_outpatient.xlsx \
      --version v5.26 --effective 2026-01-01 --out data/va_charges_normalized.csv

  # also cache the public inpatient files for citations
  python scripts/fetch_va_charges.py --fetch-public --out-dir data/va_public

The normalized CSV (gitignored) is picked up automatically by the web app's
ensure_default_va_library() on next startup. Without --outpatient the app falls
back to the labeled SAMPLE seed. The outpatient/professional table is behind the
VA's AMA CPT-Code disclaimer; download it once (a click you are entitled to make)
and pass the saved .xlsx here. CPT(R) is AMA-copyrighted; your CPT license
governs internal use, which is why the normalized file is gitignored.
"""

from __future__ import annotations

import argparse
import csv
import sys
import urllib.request
from pathlib import Path

# Directly-downloadable public VA files (inpatient MS-DRG / SNF per-diem tables).
PUBLIC_FILES = {
    "inpatient_table_a_v5-25.xlsx":
        "https://www.va.gov/COMMUNITYCARE/docs/RO/Inpatient-DataTables/v5-25-Table-A.xlsx",
    "inpatient_table_b_v5-25.xlsx":
        "https://www.va.gov/COMMUNITYCARE/docs/RO/Inpatient-DataTables/v5-25-Table-B.xlsx",
}


def _ingest_outpatient(path: str, version: str, effective: str, out: str) -> int:
    from palcp.pricing.va import load_va_outpatient
    table = load_va_outpatient(path, version=version, effective_date=effective)
    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "code", "code_type", "description", "amount",
                    "percentile", "geographic_area", "effective_date", "citation_url"])
        for r in table.records:
            w.writerow([r.source, r.code, r.code_type, r.description, r.amount,
                        r.percentile if r.percentile is not None else "",
                        r.geographic_area, r.effective_date, r.citation_url])
    return len(table.records)


def _fetch_public(out_dir: str) -> None:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    for name, url in PUBLIC_FILES.items():
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(url, d / name)  # noqa: S310 (trusted gov URL)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outpatient", help="path to official VA outpatient .xlsx")
    ap.add_argument("--version", default="v5.26")
    ap.add_argument("--effective", default="2026-01-01")
    ap.add_argument("--out", default="data/va_charges_normalized.csv")
    ap.add_argument("--fetch-public", action="store_true")
    ap.add_argument("--out-dir", default="data/va_public")
    args = ap.parse_args(argv)

    if args.fetch_public:
        _fetch_public(args.out_dir)
    if args.outpatient:
        n = _ingest_outpatient(args.outpatient, args.version, args.effective, args.out)
        print(f"wrote {n} VA charge rows -> {args.out}")
    if not args.fetch_public and not args.outpatient:
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

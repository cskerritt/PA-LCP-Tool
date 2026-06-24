"""Load the official VA Reasonable Charges outpatient/professional workbook.

The VA publishes outpatient & professional charges keyed by CPT/HCPCS, with a
geographic component (3-digit ZIP / GAAF). The exact column layout varies by
release, so this loader builds on the flexible ``load_pricing`` preset machinery
and stamps every row with the VA source + version + effective date + citation.

It tolerates real-world quirks already handled by ``load_pricing`` ('BR'/by
report, 'N/A', '$'/','/space) by skipping non-numeric charge rows rather than
aborting. The SAMPLE seed (``SEED_PATH``) is synthetic and clearly labeled.
"""

from __future__ import annotations

from pathlib import Path

from .loaders import load_pricing
from .schema import PriceRecord, PricingTable

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "va_charges_seed.csv"
VA_CITATION = "https://www.va.gov/COMMUNITYCARE/revenue-ops/payer-rates.asp"


def load_va_outpatient(
    path: str | Path,
    *,
    version: str,
    effective_date: str,
    sheet: str | None = None,
) -> PricingTable:
    """Normalize a VA outpatient/professional workbook into a PricingTable.

    ``version`` (e.g. "v5.26") names the release; ``effective_date`` its start.
    The seed CSV already uses canonical columns; official files map via the
    ``va_reasonable_charges`` preset (code=CPT/HCPCS, description, amount=Charge,
    geographic_area=Geographic Area).
    """
    raw = load_pricing(path, preset="va_reasonable_charges", sheet=sheet)
    source = f"VA Reasonable Charges {version}"
    out = PricingTable()
    for r in raw.records:
        out.add(PriceRecord(
            source=(r.source if "SAMPLE" in (r.source or "") else source),
            code=r.code,
            amount=r.amount,
            code_type=r.code_type or "CPT/HCPCS",
            description=r.description,
            percentile=r.percentile,
            geographic_area=r.geographic_area,
            effective_date=r.effective_date or effective_date,
            citation_url=r.citation_url or VA_CITATION,
        ))
    return out

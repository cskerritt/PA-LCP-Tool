"""Bridge the VA charge engine into the web app: compute localized charges on
demand from the bundled (gitignored) ``data/va_charges.sqlite`` dataset.

If the dataset is absent (only the labeled SAMPLE seed is loaded), every helper
returns ``None``/empty and the app falls back to the flat SAMPLE pricing library.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from palcp import PriceRecord
from palcp.pricing.va_charges import VACharge, VADataset, best_charge, compute_charge
from palcp.pricing.growth_map import category_hint, growth_key_for
from palcp.pricing.va_ingest import from_sqlite

# Path to the built VA dataset. Overridable via PALCP_VA_DATASET (empty string =
# disabled, so tests stay hermetic on the labeled SAMPLE seed).
VA_DATASET_PATH = Path(os.environ.get("PALCP_VA_DATASET", "data/va_charges.sqlite"))
VA_CITATION = "https://www.va.gov/COMMUNITYCARE/revenue-ops/payer-rates.asp"


@lru_cache(maxsize=1)
def get_va_dataset() -> Optional[VADataset]:
    """Load the full VA charge dataset once (or None if not built/disabled)."""
    if str(VA_DATASET_PATH) and VA_DATASET_PATH.exists():
        try:
            return from_sqlite(VA_DATASET_PATH)
        except Exception:  # pragma: no cover - corrupt/locked file: fall back
            return None
    return None


def va_charge_for(code: str, zip3: str, setting: str = "non_facility") -> Optional[VACharge]:
    ds = get_va_dataset()
    if ds is None:
        return None
    return best_charge(ds, code, zip3 or "", setting=setting)


def va_combinations(code: str, zip3: str, setting: str = "non_facility") -> list[VACharge]:
    """All VA charge bases for a code at a locality (the 'combinations')."""
    ds = get_va_dataset()
    if ds is None:
        return []
    return compute_charge(ds, code, zip3 or "", setting=setting)


def apply_va_pricing(case, items) -> bool:
    """Price each engine ``CareItem`` from the VA dataset at the case's ZIP.

    Mirrors ``palcp.apply_pricing`` back-fill (cost/source/desc/category/growth/
    geo/retrieval) but uses the localized VA computation and each row's
    ``va_setting``. Returns True if the dataset was available (so the caller can
    skip the flat-table path). User-entered unit costs are never overwritten.
    """
    ds = get_va_dataset()
    if ds is None:
        return False
    rows = list(case.items)
    source = f"VA Reasonable Charges {ds.version}"
    for row, item in zip(rows, items):
        if item.unit_cost and item.unit_cost > 0:
            continue  # respect a direct/user cost
        if not item.code:
            continue
        setting = getattr(row, "va_setting", None) or "non_facility"
        c = best_charge(ds, item.code, case.geo_zip3 or "", setting=setting)
        if c is None:
            continue
        item.unit_cost = c.amount
        if not item.pricing_source:
            item.pricing_source = source
        if not item.code_type:
            item.code_type = "CPT/HCPCS"
        if not item.geographic_basis:
            item.geographic_basis = c.zip3 or (case.geo_zip3 or "")
        if not item.retrieval_date:
            item.retrieval_date = ds.effective_date
        if not item.description and c.description:
            item.description = c.description
        if (not item.category) or item.category == "Uncategorized":
            hint = category_hint(item.code, item.code_type)
            if hint != "Uncategorized":
                item.category = hint
        if (not item.growth_key) or item.growth_key == "medical_services":
            item.growth_key = growth_key_for(item.code, item.code_type)
    return True


def va_price_record(c: VACharge) -> PriceRecord:
    """A PriceRecord view of a computed VA charge (for the lookup fragment)."""
    ds = get_va_dataset()
    ver = ds.version if ds else "v5.26"
    eff = ds.effective_date if ds else ""
    return PriceRecord(
        source=f"VA Reasonable Charges {ver}", code=c.code, amount=c.amount,
        code_type="CPT/HCPCS", description=c.description, geographic_area=c.zip3,
        effective_date=eff, citation_url=VA_CITATION)

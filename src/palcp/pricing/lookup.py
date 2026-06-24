"""Resolve a :class:`~palcp.models.CareItem`'s unit cost from a pricing table.

A care item may carry its ``unit_cost`` directly (e.g. a direct vendor survey --
the gold standard under Consensus Statement 85), or it may reference a ``code``
to be priced from a :class:`~palcp.pricing.schema.PricingTable`.  This module
performs that lookup with a transparent, deterministic preference order and
records exactly which record was used so the choice is auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models import CareItem
from .growth_map import category_hint, growth_key_for
from .schema import PriceRecord, PricingTable


@dataclass
class Resolution:
    """The outcome of pricing one care item."""

    item: CareItem
    unit_cost: float
    record: Optional[PriceRecord]  # None when the item carried its own price
    method: str  # "direct" | "matched" | "unresolved"
    note: str = ""


def _score(record: PriceRecord, item: CareItem) -> tuple:
    """Higher tuples sort first: prefer source match, then percentile match,
    then geographic match, then a defined percentile, then higher amount."""
    src_match = int(
        bool(item.pricing_source)
        and item.pricing_source.lower() in (record.source or "").lower()
    )
    pct_match = int(
        item.percentile is not None
        and record.percentile is not None
        and abs(record.percentile - item.percentile) < 1e-6
    )
    geo_match = int(
        bool(item.geographic_basis)
        and item.geographic_basis.lower() in (record.geographic_area or "").lower()
    )
    has_pct = int(record.percentile is not None)
    return (src_match, pct_match, geo_match, has_pct, record.amount)


def resolve_item(
    item: CareItem, table: Optional[PricingTable] = None
) -> Resolution:
    """Return the unit cost to use for ``item``.

    * If the item already has a positive ``unit_cost``, it is used as-is
      (``method="direct"``).
    * Otherwise, if a ``code`` and ``table`` are available, the best-matching
      record is selected (``method="matched"``).
    * Failing both, ``method="unresolved"`` with ``unit_cost=0.0``.
    """
    if item.unit_cost and item.unit_cost > 0:
        return Resolution(item, float(item.unit_cost), None, "direct")

    if table is not None and item.code:
        matches = table.by_code(item.code)
        if matches:
            best = max(matches, key=lambda r: _score(r, item))
            note = f"Priced from {best.source} (code {best.code})"
            if best.percentile is not None:
                note += f", {best.percentile:g}th pct"
            return Resolution(item, float(best.amount), best, "matched", note)

    return Resolution(
        item,
        0.0,
        None,
        "unresolved",
        f"No price found for code {item.code!r} and no direct unit_cost supplied.",
    )


def apply_pricing(
    items: list[CareItem], table: Optional[PricingTable] = None
) -> list[Resolution]:
    """Resolve a list of items, mutating each item's ``unit_cost``/metadata in
    place when a matched record fills a gap.  Returns the resolutions for audit.
    """
    resolutions: list[Resolution] = []
    for item in items:
        res = resolve_item(item, table)
        if res.method == "matched" and res.record is not None:
            item.unit_cost = res.unit_cost
            if not item.pricing_source:
                item.pricing_source = res.record.source
            if not item.code_type:
                item.code_type = res.record.code_type
            if not item.geographic_basis:
                item.geographic_basis = res.record.geographic_area
            if item.percentile is None:
                item.percentile = res.record.percentile
            if not item.retrieval_date:
                item.retrieval_date = res.record.effective_date
            if not item.description and res.record.description:
                item.description = res.record.description
            if (not item.category) or item.category == "Uncategorized":
                hint = category_hint(item.code, item.code_type or res.record.code_type)
                if hint != "Uncategorized":
                    item.category = hint
            if (not item.growth_key) or item.growth_key == "medical_services":
                item.growth_key = growth_key_for(
                    item.code, item.code_type or res.record.code_type)
        resolutions.append(res)
    return resolutions

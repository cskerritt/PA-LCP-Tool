"""Canonical pricing-table schema.

Pricing data comes from many vendors (MFUS/Context4, Yale Wasserman, VA
Reasonable Charges, CMS DMEPOS, Genworth, direct vendor surveys).  Each arrives
in its own column layout.  We normalise everything into a single
:class:`PriceRecord` shape so the rest of the tool -- and the audit trail in the
final workbook -- is source-agnostic but never loses provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PriceRecord:
    """One priced line from a fee schedule / charge database."""

    source: str  # e.g. "VA Reasonable Charges 2024"
    code: str  # CPT / HCPCS / APC / MS-DRG
    amount: float  # the charge / allowed amount, in dollars
    code_type: str = ""  # "CPT" | "HCPCS" | ...
    description: str = ""
    percentile: Optional[float] = None  # e.g. 80 if this is the 80th-%ile charge
    geographic_area: str = ""  # locality / ZIP3 / fee-schedule area / "national"
    effective_date: str = ""  # version / effective date of the schedule
    citation_url: str = ""

    @property
    def key(self) -> str:
        return normalize_code(self.code)


def normalize_code(code: str) -> str:
    """Normalise a procedure code for matching (uppercase, stripped)."""
    return str(code or "").strip().upper()


@dataclass
class PricingTable:
    """A searchable collection of :class:`PriceRecord` objects."""

    records: list[PriceRecord] = field(default_factory=list)
    _index: dict[str, list[PriceRecord]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._reindex()

    def _reindex(self) -> None:
        self._index = {}
        for r in self.records:
            self._index.setdefault(r.key, []).append(r)

    def add(self, record: PriceRecord) -> None:
        self.records.append(record)
        self._index.setdefault(record.key, []).append(record)

    def extend(self, records: list[PriceRecord]) -> None:
        for r in records:
            self.add(r)

    def by_code(self, code: str) -> list[PriceRecord]:
        return list(self._index.get(normalize_code(code), []))

    @property
    def sources(self) -> list[str]:
        seen: list[str] = []
        for r in self.records:
            if r.source not in seen:
                seen.append(r.source)
        return seen

    def __len__(self) -> int:
        return len(self.records)

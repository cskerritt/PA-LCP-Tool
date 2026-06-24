"""VA Reasonable Charges computation engine (localized to a 3-digit ZIP).

Pure, deterministic. Given a :class:`VADataset` (national charge bases + GAAF
tables + conversion factors + modifiers, ingested from the official VA v5.26
workbooks), :func:`compute_charge` returns the VA reasonable charge for a
CPT/HCPCS code at a given 3-digit ZIP, for every table the code appears in (a
code can have several "combinations" — e.g. an outpatient-facility charge and a
professional read).

Formula (encodes the published VA methodology, 38 CFR 17.101):
  * direct-charge tables (F/K/C/D/E/I/A/B):  charge x GAAF[zip3]
  * RVU-based tables (G/J/H):  RVU x ConversionFactor[category] x GAAF[zip3, category]
    where RVU = work + practice-expense (non-facility by default, facility
    optional), or the table's total-expense RVU when that is the populated total.
Nothing is fabricated: an unknown code yields no charge; a basis whose locality
GAAF is missing falls back to the national charge and says so in the breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .schema import normalize_code


def normalize_zip3(value) -> str:
    """First 3 digits of a ZIP, zero-padded (e.g. 5 -> '005', '19103' -> '191')."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return ""
    return digits[:3].zfill(3) if len(digits) >= 3 else digits.zfill(3)


@dataclass(frozen=True)
class VAChargeBasis:
    """One national charge basis for a code in one VA table."""

    code: str
    table: str  # 'F','G','J','K',...
    charge_type: str  # human label, e.g. "Outpatient Facility"
    description: str = ""
    # direct-charge tables:
    charge: Optional[float] = None
    # RVU-based tables:
    work_rvu: Optional[float] = None
    facility_pe_rvu: Optional[float] = None
    nonfacility_pe_rvu: Optional[float] = None
    total_expense_rvu: Optional[float] = None
    cf_category: Optional[str] = None
    # geography:
    gaaf_table: str = ""  # 'L','P','Q','N','O','R'
    gaaf_category: Optional[str] = None
    methodology: str = ""
    status_indicator: str = ""
    modifier: str = ""

    @property
    def is_direct(self) -> bool:
        return self.charge is not None


@dataclass(frozen=True)
class VACharge:
    """A computed, locality-adjusted VA reasonable charge."""

    code: str
    table: str
    charge_type: str
    description: str
    amount: float  # localized, rounded to cents
    national: float  # national (GAAF = 1.0), rounded to cents
    zip3: str
    gaaf: float
    setting: str  # "facility" | "non_facility"
    methodology: str
    breakdown: str  # human-readable formula


@dataclass
class VADataset:
    """National charge bases + GAAF + conversion factors + modifiers."""

    bases: dict[str, list[VAChargeBasis]] = field(default_factory=dict)
    cf: dict[str, float] = field(default_factory=dict)
    gaaf: dict[tuple, float] = field(default_factory=dict)  # (table, zip3, category) -> factor
    modifier: dict[str, float] = field(default_factory=dict)
    version: str = ""
    effective_date: str = ""

    def bases_for(self, code: str) -> list[VAChargeBasis]:
        return self.bases.get(normalize_code(code), [])

    def gaaf_for(self, table: str, zip3: str, category: Optional[str]) -> Optional[float]:
        return self.gaaf.get((table, normalize_zip3(zip3), category))


def _rvu_total(b: VAChargeBasis, setting: str) -> Optional[float]:
    if b.total_expense_rvu is not None:
        return b.total_expense_rvu
    pe = b.facility_pe_rvu if setting == "facility" else b.nonfacility_pe_rvu
    if b.work_rvu is None and pe is None:
        return None
    return (b.work_rvu or 0.0) + (pe or 0.0)


def compute_charge(
    ds: VADataset,
    code: str,
    zip3: str,
    *,
    setting: str = "non_facility",
    modifier: Optional[str] = None,
) -> list[VACharge]:
    """Return one :class:`VACharge` per basis the code has (possibly empty)."""
    zip3 = normalize_zip3(zip3)
    results: list[VACharge] = []
    for b in ds.bases_for(code):
        if b.is_direct:
            national = float(b.charge)
            base_note = f"{b.charge_type} charge ${national:,.2f}"
        else:
            rvu = _rvu_total(b, setting)
            cf = ds.cf.get(b.cf_category) if b.cf_category else None
            if rvu is None or cf is None:
                continue  # cannot price without RVU + conversion factor
            national = rvu * cf
            base_note = (f"{rvu:g} RVU x CF {cf:g} ({b.cf_category})"
                         f" [{setting.replace('_', '-')}]")

        g = ds.gaaf_for(b.gaaf_table, zip3, b.gaaf_category)
        if g is None:
            gaaf, geo_note = 1.0, f"no GAAF for ZIP {zip3}; national charge used"
        else:
            gaaf, geo_note = float(g), (f"x GAAF {g:g} (Table {b.gaaf_table}"
                                        f", ZIP {zip3})")

        amount = national * gaaf
        mod_note = ""
        if modifier:
            mf = ds.modifier.get(modifier, 1.0)
            amount *= mf
            mod_note = f" x modifier {modifier} ({mf:g})"

        results.append(VACharge(
            code=normalize_code(code), table=b.table, charge_type=b.charge_type,
            description=b.description, amount=round(amount, 2),
            national=round(national, 2), zip3=zip3, gaaf=gaaf, setting=setting,
            methodology=b.methodology, breakdown=f"{base_note} {geo_note}{mod_note}"))
    return results


# LCP relevance order for picking a single charge when a bare code is looked up.
_LCP_TABLE_PRIORITY = {"G": 0, "J": 1, "F": 2, "K": 3, "I": 4, "E": 5,
                       "H": 6, "C": 7, "D": 8, "A": 9, "B": 10}
# Radiology/imaging codes (CPT 70000-79999) are costed at the global/facility
# charge in an LCP, so prefer the outpatient-facility (F) table over the
# professional-only read (G).
_RADIOLOGY_PRIORITY = {"F": 0, "G": 1, "J": 2, "K": 3, "I": 4, "E": 5,
                       "H": 6, "C": 7, "D": 8, "A": 9, "B": 10}


def _is_radiology(code: str) -> bool:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(digits) != 5:
        return False
    return 70000 <= int(digits) <= 79999


def best_charge(
    ds: VADataset, code: str, zip3: str, *, setting: str = "non_facility",
    modifier: Optional[str] = None,
) -> Optional[VACharge]:
    """Pick the most LCP-relevant single charge for a bare code lookup.

    Radiology (CPT 70000-79999) prefers the outpatient-facility/global charge;
    everything else prefers the professional charge, then lab, facility, DME, etc.
    Returns ``None`` if the code has no VA basis.
    """
    charges = compute_charge(ds, code, zip3, setting=setting, modifier=modifier)
    if not charges:
        return None
    order = _RADIOLOGY_PRIORITY if _is_radiology(code) else _LCP_TABLE_PRIORITY
    return min(charges, key=lambda c: order.get(c.table, 99))

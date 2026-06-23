"""Core domain model for the PA-LCP-Tool life-care-plan cost projection engine.

Every object here is a plain ``dataclass`` with explicit, documented fields so
that the inputs to a projection are transparent and reproducible -- a core
requirement for admissibility under *Daubert v. Merrell Dow* and Federal Rule
of Evidence 702.  Nothing in this module performs economic math; it only
describes *what was assumed*.  The math lives in :mod:`palcp.economics`.

Glossary
--------
base year / valuation date
    The date the report is prepared.  All ``unit_cost`` values are expressed in
    *current* (base-year) dollars.  Growth and discounting are measured from
    this date.
horizon
    The number of years over which care is projected, driven by the claimant's
    life expectancy (see :class:`LifeExpectancy`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------------- #
# Economic assumptions
# --------------------------------------------------------------------------- #
@dataclass
class GrowthRate:
    """A published price-growth (medical inflation) series applied to a class
    of care items.

    Keeping the ``source``/``citation``/``as_of`` fields mandatory enforces the
    *transparency* domain of life-care-plan peer review: every rate must trace
    to a verifiable, dated, published source.
    """

    key: str  # machine key referenced by CareItem.growth_key, e.g. "medical_services"
    label: str  # human label, e.g. "Medical Care Services (CPI-U)"
    annual_rate: float  # decimal, e.g. 0.032 for 3.2% per year
    source: str = ""  # e.g. "BLS CPI-U, Medical Care Services, series CUUR0000SAM2"
    citation_url: str = ""
    as_of: str = ""  # date the rate was retrieved / period it represents
    note: str = ""

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("GrowthRate.key is required")


@dataclass
class DiscountRate:
    """The rate used to reduce future nominal dollars to present value.

    ``basis`` documents whether ``annual_rate`` is a *nominal* market rate
    (paired with nominal growth) or a *real* (inflation-adjusted) rate such as a
    TIPS yield (paired with a net-discount approach).  ``timing`` selects when
    within each year a cash flow is assumed to occur.
    """

    annual_rate: float  # decimal, e.g. 0.043
    basis: str = "nominal"  # "nominal" | "real"
    timing: str = "mid_year"  # "begin_year" | "mid_year" | "end_year"
    source: str = ""  # e.g. "U.S. Treasury 20-Year Constant Maturity"
    citation_url: str = ""
    as_of: str = ""

    VALID_TIMINGS = ("begin_year", "mid_year", "end_year")
    VALID_BASES = ("nominal", "real")

    def __post_init__(self) -> None:
        if self.timing not in self.VALID_TIMINGS:
            raise ValueError(
                f"DiscountRate.timing must be one of {self.VALID_TIMINGS}, got {self.timing!r}"
            )
        if self.basis not in self.VALID_BASES:
            raise ValueError(
                f"DiscountRate.basis must be one of {self.VALID_BASES}, got {self.basis!r}"
            )


@dataclass
class LifeExpectancy:
    """The duration-of-care multiplier for the whole plan.

    Per IALCP methodology and the *Anderson-Moody* / *Gunn* line of cases, a
    non-physician life-care planner does **not** independently reduce life
    expectancy; a reduced figure must come from a qualified medical/mortality
    opinion.  ``note`` should record which applies.
    """

    age_at_report: float
    additional_years: float  # remaining life expectancy in years (may be fractional)
    source: str = ""  # e.g. "CDC/NCHS United States Life Tables, 2021, Table B"
    citation_url: str = ""
    as_of: str = ""
    note: str = ""  # e.g. "Unimpaired period life table; not medically reduced."

    @property
    def terminal_age(self) -> float:
        return self.age_at_report + self.additional_years


@dataclass
class Claimant:
    """Identity and the geographic basis used for pricing."""

    name: str = ""
    dob: str = ""
    sex: str = ""
    age_at_report: Optional[float] = None
    residence: str = ""  # county/ZIP/region used to geo-localize pricing
    notes: str = ""


# --------------------------------------------------------------------------- #
# Care items (the line items of the plan)
# --------------------------------------------------------------------------- #
@dataclass
class CareItem:
    """A single recommended good or service in the life care plan.

    Exactly one *timing pattern* should be supplied:

    * recurring annual care -> ``frequency_per_year`` (e.g. ``2`` = twice/yr;
      ``0.5`` = every other year is also valid, but prefer ``every_n_years``);
    * periodic replacement -> ``every_n_years`` (e.g. wheelchair every ``5`` yr);
    * a single future event -> ``one_time=True`` with ``one_time_age``.

    ``unit_cost`` is the current (base-year) cost for one occurrence *before*
    multiplying by ``units_per_occurrence``.  It may be entered directly or
    resolved from a :class:`~palcp.pricing.schema.PricingTable` by ``code``.

    ``medical_foundation`` is the citation tying the item to a treating
    physician/record (e.g. "Dr. Chhatre IME 5/7/2025, p.14").  Items lacking it
    are flagged by the validator -- this is the single most common ground for
    *Daubert* exclusion (*Gunn v. Atchison*, *Anderson-Moody v. Wilson*).
    """

    category: str
    item: str
    unit_cost: float
    description: str = ""
    code: str = ""  # CPT / HCPCS / APC / MS-DRG
    code_type: str = ""  # "CPT" | "HCPCS" | "APC" | "MS-DRG" | ...
    pricing_source: str = ""  # e.g. "MFUS 80th %ile", "VA Reasonable Charges"
    percentile: Optional[float] = None  # e.g. 80 for the 80th percentile
    geographic_basis: str = ""  # ZIP / locality / GAF / national
    retrieval_date: str = ""

    units_per_occurrence: float = 1.0
    frequency_per_year: Optional[float] = None
    every_n_years: Optional[float] = None
    one_time: bool = False
    one_time_age: Optional[float] = None

    start_age: Optional[float] = None  # None => begins at age_at_report
    end_age: Optional[float] = None  # None => continues to terminal age

    growth_key: str = "medical_services"
    medical_foundation: str = ""
    notes: str = ""

    @property
    def cost_per_occurrence(self) -> float:
        return float(self.unit_cost) * float(self.units_per_occurrence)


# --------------------------------------------------------------------------- #
# Top-level plan
# --------------------------------------------------------------------------- #
@dataclass
class Plan:
    """A complete life care plan: case metadata, economic assumptions, and items."""

    claimant: Claimant
    life_expectancy: LifeExpectancy
    discount_rate: DiscountRate
    growth_rates: dict[str, GrowthRate]
    items: list[CareItem] = field(default_factory=list)

    # Report / methodology metadata (all appear on the workbook tabs)
    report_date: str = ""
    base_year: Optional[int] = None
    evaluator: str = ""
    evaluator_credentials: str = ""
    jurisdiction: str = ""
    matter: str = ""  # caption / case name
    percentile_policy: float = 80.0  # default reasonable-value percentile
    collateral_source_note: str = ""
    rounding: int = 2

    def growth_rate_for(self, item: CareItem) -> GrowthRate:
        """Return the :class:`GrowthRate` governing ``item``.

        Raises ``KeyError`` with an actionable message if the item references an
        undefined growth key -- a configuration error we never want to silently
        paper over with a default rate.
        """
        try:
            return self.growth_rates[item.growth_key]
        except KeyError as exc:  # pragma: no cover - exercised via validator
            raise KeyError(
                f"Care item {item.item!r} references growth_key "
                f"{item.growth_key!r}, which is not defined in growth_rates "
                f"(defined keys: {sorted(self.growth_rates)})."
            ) from exc

    def to_dict(self) -> dict:
        """Serialise for debugging / round-tripping (not used by the engine)."""
        return {
            "claimant": asdict(self.claimant),
            "life_expectancy": asdict(self.life_expectancy),
            "discount_rate": asdict(self.discount_rate),
            "growth_rates": {k: asdict(v) for k, v in self.growth_rates.items()},
            "items": [asdict(i) for i in self.items],
            "report_date": self.report_date,
            "base_year": self.base_year,
            "evaluator": self.evaluator,
            "evaluator_credentials": self.evaluator_credentials,
            "jurisdiction": self.jurisdiction,
            "matter": self.matter,
            "percentile_policy": self.percentile_policy,
            "collateral_source_note": self.collateral_source_note,
            "rounding": self.rounding,
        }

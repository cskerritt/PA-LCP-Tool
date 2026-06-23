"""The cost-projection engine.

This module turns a :class:`~palcp.models.Plan` into a fully itemised,
year-by-year projection in three measures:

* **current cost** -- base-year (today's) dollars, *no* growth, *no* discount.
  This is the classic life-care-plan "current cost" table.
* **nominal (future) cost** -- current cost grown by the item's published
  medical-inflation series to the year the cost is incurred.
* **present value** -- nominal cost discounted back to the valuation date.

Convention (documented for the report and for cross-examination)
----------------------------------------------------------------
Let ``y = 0, 1, 2, ...`` index projection years (Year 1 is ``y = 0``).  The
claimant's age at the start of year ``y`` is ``age_at_report + y``.

A single *time exponent* ``m(y)`` -- the time in years from the valuation date
to the assumed cash-flow date -- is used for **both** growth and discounting so
the two are perfectly consistent:

================  ===========================  ===================================
``timing``        ``m(y)``                     interpretation
================  ===========================  ===================================
``begin_year``    ``y``                        cash flows at the start of the year
``mid_year``      ``y + 0.5``                  cash flows at mid-year (default)
``end_year``      ``y + 1``                    cash flows at year-end
================  ===========================  ===================================

For an item with growth rate ``g`` and a portfolio discount rate ``d``::

    nominal_i(y) = base_i(y) * (1 + g) ** m(y)
    pv_i(y)      = nominal_i(y) / (1 + d) ** m(y)
                 = base_i(y) / (1 + r_i) ** m(y),   r_i = (1+d)/(1+g) - 1

where ``r_i`` is the *net discount rate* for that item (reported on the
Assumptions tab).  Because growth is item-specific but discounting is uniform,
the present value of a whole year equals that year's total nominal cost times a
single discount factor ``1 / (1 + d) ** m(y)``.

The final (partial) year of life expectancy is prorated by the fractional part
of the remaining-years figure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..models import CareItem, Plan


# --------------------------------------------------------------------------- #
# Timing
# --------------------------------------------------------------------------- #
_TIMING_OFFSET = {"begin_year": 0.0, "mid_year": 0.5, "end_year": 1.0}


def time_exponent(year_index: int, timing: str) -> float:
    """Years from valuation date to the assumed cash-flow date of ``year_index``."""
    try:
        return float(year_index) + _TIMING_OFFSET[timing]
    except KeyError as exc:  # pragma: no cover - guarded by DiscountRate
        raise ValueError(f"Unknown timing convention: {timing!r}") from exc


def net_discount_rate(discount: float, growth: float) -> float:
    """Return r such that (1+d) = (1+g)(1+r); i.e. the growth-adjusted discount."""
    return (1.0 + discount) / (1.0 + growth) - 1.0


# --------------------------------------------------------------------------- #
# Result objects
# --------------------------------------------------------------------------- #
@dataclass
class ItemResult:
    """Per-item lifetime aggregates."""

    item: CareItem
    growth_rate: float
    net_discount_rate: float
    occurrences_total: float
    first_age: Optional[float]
    last_age: Optional[float]
    active_years: float  # weighted count of years the item is active
    current_total: float  # base-year dollars, undiscounted
    nominal_total: float  # future dollars, grown
    present_value: float  # discounted to valuation date


@dataclass
class YearResult:
    """Totals for a single projection year, broken out by category."""

    year_index: int
    calendar_year: Optional[int]
    age_start: float
    weight: float
    discount_factor: float
    by_category_current: dict[str, float] = field(default_factory=dict)
    by_category_nominal: dict[str, float] = field(default_factory=dict)
    by_category_pv: dict[str, float] = field(default_factory=dict)

    @property
    def total_current(self) -> float:
        return sum(self.by_category_current.values())

    @property
    def total_nominal(self) -> float:
        return sum(self.by_category_nominal.values())

    @property
    def total_pv(self) -> float:
        return sum(self.by_category_pv.values())


@dataclass
class ProjectionResult:
    plan: Plan
    item_results: list[ItemResult]
    year_results: list[YearResult]
    categories: list[str]

    @property
    def grand_total_current(self) -> float:
        return sum(r.current_total for r in self.item_results)

    @property
    def grand_total_nominal(self) -> float:
        return sum(r.nominal_total for r in self.item_results)

    @property
    def grand_total_present_value(self) -> float:
        return sum(r.present_value for r in self.item_results)

    @property
    def first_year_current_cost(self) -> float:
        """Total *current-dollar* cost active in projection Year 1."""
        return self.year_results[0].total_current if self.year_results else 0.0

    def totals_by_category(self) -> dict[str, dict[str, float]]:
        """``{category: {"current":x, "nominal":y, "present_value":z}}``."""
        out: dict[str, dict[str, float]] = {
            c: {"current": 0.0, "nominal": 0.0, "present_value": 0.0}
            for c in self.categories
        }
        for r in self.item_results:
            bucket = out.setdefault(
                r.item.category,
                {"current": 0.0, "nominal": 0.0, "present_value": 0.0},
            )
            bucket["current"] += r.current_total
            bucket["nominal"] += r.nominal_total
            bucket["present_value"] += r.present_value
        return out


# --------------------------------------------------------------------------- #
# Per-item occurrence model
# --------------------------------------------------------------------------- #
def _active(item: CareItem, age_start: float) -> bool:
    """Is ``item`` active in a year that begins at ``age_start``?

    Active when ``start_age <= age_start < end_age`` (open at the top so that an
    item ending at age 65 covers ages up to but not including 65).
    """
    if item.start_age is not None and age_start < item.start_age - 1e-9:
        return False
    if item.end_age is not None and age_start >= item.end_age - 1e-9:
        return False
    return True


def occurrences_by_year(item: CareItem, ages_start: list[float]) -> list[float]:
    """Return the number of occurrences of ``item`` in each projection year.

    ``ages_start[y]`` is the claimant's age at the start of year ``y``.
    """
    n = len(ages_start)
    occ = [0.0] * n

    # One-time event: a single occurrence in the year that contains one_time_age.
    if item.one_time:
        target = item.one_time_age
        if target is None:
            target = item.start_age if item.start_age is not None else ages_start[0]
        for y, a in enumerate(ages_start):
            if a - 1e-9 <= target < a + 1.0 - 1e-9:
                occ[y] = 1.0
                break
        return occ

    # Periodic replacement: every N years, anchored at the first active year.
    if item.every_n_years:
        step = max(1, int(round(item.every_n_years)))
        first = next((y for y, a in enumerate(ages_start) if _active(item, a)), None)
        if first is None:
            return occ
        y = first
        while y < n and _active(item, ages_start[y]):
            occ[y] = 1.0
            y += step
        return occ

    # Recurring annual care.
    freq = item.frequency_per_year if item.frequency_per_year is not None else 0.0
    for y, a in enumerate(ages_start):
        if _active(item, a):
            occ[y] = float(freq)
    return occ


# --------------------------------------------------------------------------- #
# Year scaffold
# --------------------------------------------------------------------------- #
def _year_scaffold(plan: Plan) -> tuple[list[float], list[float], list[Optional[int]]]:
    """Return (ages_start, weights, calendar_years) for each projection year."""
    le = plan.life_expectancy.additional_years
    full = int(math.floor(le + 1e-9))
    frac = le - full

    ages_start: list[float] = []
    weights: list[float] = []
    calendar_years: list[Optional[int]] = []

    age0 = plan.life_expectancy.age_at_report
    for y in range(full):
        ages_start.append(age0 + y)
        weights.append(1.0)
        calendar_years.append((plan.base_year + y) if plan.base_year else None)
    if frac > 1e-9:
        ages_start.append(age0 + full)
        weights.append(frac)
        calendar_years.append((plan.base_year + full) if plan.base_year else None)
    return ages_start, weights, calendar_years


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def project(plan: Plan) -> ProjectionResult:
    """Run the full projection for ``plan`` and return a :class:`ProjectionResult`."""
    ages_start, weights, calendar_years = _year_scaffold(plan)
    n = len(ages_start)
    timing = plan.discount_rate.timing
    d = plan.discount_rate.annual_rate

    # Stable, first-seen category ordering.
    categories: list[str] = []
    for it in plan.items:
        if it.category not in categories:
            categories.append(it.category)

    # Per-year discount factors and growth factors (growth is per-rate).
    m = [time_exponent(y, timing) for y in range(n)]
    discount_factor = [1.0 / (1.0 + d) ** m[y] for y in range(n)]
    growth_factor: dict[str, list[float]] = {}
    for key, gr in plan.growth_rates.items():
        growth_factor[key] = [(1.0 + gr.annual_rate) ** m[y] for y in range(n)]

    year_results = [
        YearResult(
            year_index=y,
            calendar_year=calendar_years[y],
            age_start=ages_start[y],
            weight=weights[y],
            discount_factor=discount_factor[y],
            by_category_current={c: 0.0 for c in categories},
            by_category_nominal={c: 0.0 for c in categories},
            by_category_pv={c: 0.0 for c in categories},
        )
        for y in range(n)
    ]

    item_results: list[ItemResult] = []
    for it in plan.items:
        gr = plan.growth_rate_for(it)  # raises on unknown key (caught upstream)
        gfac = growth_factor[it.growth_key]
        occ = occurrences_by_year(it, ages_start)
        cpo = it.cost_per_occurrence

        cur_total = nom_total = pv_total = occ_total = 0.0
        first_age = last_age = None
        active_years = 0.0

        for y in range(n):
            if occ[y] == 0.0:
                continue
            w = weights[y]
            base = occ[y] * cpo * w  # current dollars for this year (weighted)
            nominal = base * gfac[y]
            pv = nominal * discount_factor[y]

            year_results[y].by_category_current[it.category] += base
            year_results[y].by_category_nominal[it.category] += nominal
            year_results[y].by_category_pv[it.category] += pv

            cur_total += base
            nom_total += nominal
            pv_total += pv
            occ_total += occ[y] * w
            active_years += w
            if first_age is None:
                first_age = ages_start[y]
            last_age = ages_start[y]

        item_results.append(
            ItemResult(
                item=it,
                growth_rate=gr.annual_rate,
                net_discount_rate=net_discount_rate(d, gr.annual_rate),
                occurrences_total=occ_total,
                first_age=first_age,
                last_age=last_age,
                active_years=active_years,
                current_total=cur_total,
                nominal_total=nom_total,
                present_value=pv_total,
            )
        )

    return ProjectionResult(
        plan=plan,
        item_results=item_results,
        year_results=year_results,
        categories=categories,
    )

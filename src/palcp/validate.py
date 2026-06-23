"""Daubert / FRE 702 pre-flight validation.

The case law on excluded life care plans is remarkably consistent about *why*
plans fail: no medical foundation for an item (*Gunn v. Atchison*,
*Anderson-Moody v. Wilson*), inconsistent / "cherry-picked" cost percentiles,
un-sourced or undated pricing, and speculative durations.  This module walks a
:class:`~palcp.models.Plan` and reports those exact defects *before* a workbook
is generated, mapped to the six peer-review domains (Barros-Bailey et al.).

It does not block generation -- a planner may have a documented reason -- but
every finding is surfaced on the workbook's Validation tab and on the console so
nothing reaches a deposition unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import CareItem, Plan

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

_SEVERITY_ORDER = {ERROR: 0, WARN: 1, INFO: 2}


@dataclass
class Finding:
    severity: str  # ERROR | WARN | INFO
    domain: str  # peer-review domain, e.g. "Medical Foundation"
    message: str
    item: Optional[str] = None  # care item name, when item-specific

    def __str__(self) -> str:
        prefix = f"[{self.severity}] ({self.domain})"
        if self.item:
            return f"{prefix} {self.item}: {self.message}"
        return f"{prefix} {self.message}"


@dataclass
class ValidationReport:
    findings: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARN]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == INFO]

    @property
    def ok(self) -> bool:
        return not self.errors

    def sorted(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (_SEVERITY_ORDER[f.severity], f.domain, f.item or ""),
        )

    def summary(self) -> str:
        return (
            f"{len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s), "
            f"{len(self.infos)} note(s)"
        )


def _item_has_timing(item: CareItem) -> bool:
    return bool(
        item.one_time
        or item.every_n_years
        or (item.frequency_per_year is not None and item.frequency_per_year != 0)
    )


def validate_plan(plan: Plan) -> ValidationReport:
    """Run all checks and return a :class:`ValidationReport`."""
    f: list[Finding] = []

    # ---- Plan-level economic foundation --------------------------------- #
    le = plan.life_expectancy
    if le.additional_years is None or le.additional_years <= 0:
        f.append(Finding(ERROR, "Findings/Conclusions",
                         "Life expectancy (additional years) must be positive."))
    if not le.source:
        f.append(Finding(WARN, "Transparency",
                         "Life expectancy has no cited source. Cite the life "
                         "table or medical/mortality opinion relied upon."))
    if not plan.discount_rate.source:
        f.append(Finding(WARN, "Transparency",
                         "Discount rate has no cited source (e.g. U.S. Treasury "
                         "constant-maturity yield as of the report date)."))
    if plan.discount_rate.basis == "real":
        f.append(Finding(INFO, "Best Practices",
                         "Discount basis is 'real'. Growth rates should then "
                         "represent medical price growth *in excess of* general "
                         "inflation, or present value will be overstated."))
    for key, gr in plan.growth_rates.items():
        if not gr.source:
            f.append(Finding(WARN, "Transparency",
                             f"Growth rate '{key}' ({gr.annual_rate:.2%}) has no "
                             f"cited source."))
    if not plan.report_date:
        f.append(Finding(INFO, "Transparency", "No report date set."))

    # ---- Per-item checks ------------------------------------------------- #
    # Track percentile usage per pricing source for cherry-picking detection.
    pct_by_source: dict[str, set] = {}

    for item in plan.items:
        name = item.item or "(unnamed item)"

        if not item.medical_foundation:
            f.append(Finding(WARN, "Medical Foundation",
                             "No medical foundation cited (treating physician / "
                             "record). Items lacking a foundation are the most "
                             "common ground for exclusion (Gunn; Anderson-Moody).",
                             item=name))

        # Pricing provenance.
        if item.unit_cost is None or item.unit_cost <= 0:
            f.append(Finding(ERROR, "Findings/Conclusions",
                             "Unit cost is zero/unresolved. Supply a direct cost "
                             "or a code that resolves against the pricing table.",
                             item=name))
        if not item.pricing_source:
            f.append(Finding(WARN, "Transparency",
                             "No pricing source named.", item=name))
        if not item.retrieval_date:
            f.append(Finding(WARN, "Transparency",
                             "No price retrieval/effective date recorded.",
                             item=name))
        if not item.geographic_basis:
            f.append(Finding(INFO, "Best Practices",
                             "No geographic basis recorded; geographic "
                             "specificity is expected (Consensus Stmt. 71/85).",
                             item=name))

        # Percentile policy / consistency.
        if item.pricing_source and item.percentile is not None:
            pct_by_source.setdefault(item.pricing_source, set()).add(item.percentile)
        if item.percentile is not None and item.percentile != plan.percentile_policy:
            f.append(Finding(INFO, "Ethical Guidelines",
                             f"Percentile {item.percentile:g} differs from the "
                             f"plan policy of {plan.percentile_policy:g}.",
                             item=name))

        # Growth mapping.
        if item.growth_key not in plan.growth_rates:
            f.append(Finding(ERROR, "Best Practices",
                             f"growth_key '{item.growth_key}' is not defined in "
                             f"the plan's growth_rates.", item=name))

        # Timing pattern sanity.
        if not _item_has_timing(item):
            f.append(Finding(WARN, "Findings/Conclusions",
                             "No timing pattern (frequency_per_year, "
                             "every_n_years, or one_time); item contributes $0.",
                             item=name))
        if (item.start_age is not None and item.end_age is not None
                and item.start_age >= item.end_age):
            f.append(Finding(ERROR, "Findings/Conclusions",
                             f"start_age ({item.start_age}) >= end_age "
                             f"({item.end_age}).", item=name))
        if item.one_time and item.one_time_age is not None:
            if not (le.age_at_report - 1e-9 <= item.one_time_age
                    <= le.terminal_age + 1e-9):
                f.append(Finding(WARN, "Findings/Conclusions",
                                 f"one_time_age ({item.one_time_age}) is outside "
                                 f"the projection window "
                                 f"[{le.age_at_report:g}, {le.terminal_age:g}]; "
                                 f"the event will not occur.", item=name))

    # Cherry-picking: same source priced at more than one percentile.
    for source, pcts in pct_by_source.items():
        if len(pcts) > 1:
            pretty = ", ".join(f"{p:g}" for p in sorted(pcts))
            f.append(Finding(WARN, "Ethical Guidelines",
                             f"Source '{source}' is used at multiple percentiles "
                             f"({pretty}). Inconsistent percentile selection "
                             f"invites a cherry-picking critique."))

    return ValidationReport(findings=f)

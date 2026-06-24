"""PA-LCP-Tool — Life Care Plan cost-projection engine and Excel report generator.

A transparent, reproducible engine for projecting the future cost of recommended
medical care and producing a court-ready Excel workbook built for admissibility
under *Daubert v. Merrell Dow* and Federal Rule of Evidence 702.

Typical use::

    from palcp import (load_plan, load_pricing, apply_pricing,
                       validate_plan, project, save_workbook)

    plan = load_plan("assumptions.yaml", "plan_items.csv")
    apply_pricing(plan.items, load_pricing("pricing.csv"))  # if pricing by code
    report = validate_plan(plan)
    result = project(plan)
    save_workbook(result, report, "life_care_plan.xlsx")
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import build_plan, load_assumptions, load_items, load_plan
from .economics import (
    ItemResult,
    LifeTable,
    ProjectionResult,
    YearResult,
    net_discount_rate,
    project,
)
from .models import (
    CareItem,
    Claimant,
    DiscountRate,
    GrowthRate,
    LifeExpectancy,
    Plan,
)
from .pricing import (
    PriceRecord,
    PricingTable,
    apply_pricing,
    load_pricing,
    resolve_item,
)
from .validate import Finding, ValidationReport, validate_plan
from .workbook import build_workbook, save_workbook

__all__ = [
    "__version__",
    # models
    "Plan",
    "Claimant",
    "CareItem",
    "GrowthRate",
    "DiscountRate",
    "LifeExpectancy",
    # config / loading
    "load_plan",
    "load_items",
    "load_assumptions",
    "build_plan",
    # pricing
    "PriceRecord",
    "PricingTable",
    "load_pricing",
    "resolve_item",
    "apply_pricing",
    # economics
    "project",
    "ProjectionResult",
    "ItemResult",
    "YearResult",
    "net_discount_rate",
    "LifeTable",
    # validation
    "validate_plan",
    "ValidationReport",
    "Finding",
    # workbook
    "build_workbook",
    "save_workbook",
]

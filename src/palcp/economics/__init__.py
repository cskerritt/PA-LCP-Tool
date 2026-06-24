"""Economic projection engine: growth, discounting, and present value."""

from .lifetable import LifeTable
from .projection import (
    ItemResult,
    ProjectionResult,
    YearResult,
    net_discount_rate,
    occurrences_by_year,
    project,
    time_exponent,
)

__all__ = [
    "LifeTable",
    "ItemResult",
    "ProjectionResult",
    "YearResult",
    "net_discount_rate",
    "occurrences_by_year",
    "project",
    "time_exponent",
]

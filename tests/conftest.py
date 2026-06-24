"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from palcp.models import (
    CareItem,
    Claimant,
    DiscountRate,
    GrowthRate,
    LifeExpectancy,
    Plan,
)


def make_growth(rate: float = 0.03, key: str = "medical_services") -> GrowthRate:
    return GrowthRate(key=key, label=key, annual_rate=rate, source="test source",
                      as_of="2026")


@pytest.fixture
def base_growth_rates() -> dict[str, GrowthRate]:
    return {
        "medical_services": make_growth(0.032, "medical_services"),
        "rx": make_growth(0.025, "rx"),
        "dme": make_growth(0.020, "dme"),
        "facility": make_growth(0.038, "facility"),
        "attendant_care_wage": make_growth(0.033, "attendant_care_wage"),
        "general": make_growth(0.024, "general"),
    }


@pytest.fixture
def simple_plan(base_growth_rates) -> Plan:
    """A 1-item, 10-year plan that is easy to reason about by hand."""
    item = CareItem(
        category="Physician Services",
        item="Office visit",
        unit_cost=100.0,
        code="99214",
        pricing_source="MFUS",
        percentile=80,
        geographic_basis="locality",
        retrieval_date="2026-05-01",
        frequency_per_year=2,
        growth_key="medical_services",
        medical_foundation="Dr. Test, note 2026-01-01",
    )
    return Plan(
        claimant=Claimant(name="Test", age_at_report=50, sex="total"),
        life_expectancy=LifeExpectancy(
            age_at_report=50, additional_years=10.0, source="CDC test"),
        discount_rate=DiscountRate(
            annual_rate=0.043, basis="nominal", timing="mid_year",
            source="Treasury test"),
        growth_rates=base_growth_rates,
        items=[item],
        report_date="2026-06-23",
        base_year=2026,
        percentile_policy=80.0,
    )

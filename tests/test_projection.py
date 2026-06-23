"""Tests for the economic projection engine."""

from __future__ import annotations

import copy
import math

import pytest

from palcp.economics import net_discount_rate, project
from palcp.economics.projection import occurrences_by_year, time_exponent
from palcp.models import CareItem


def test_time_exponent_conventions():
    assert time_exponent(0, "begin_year") == 0.0
    assert time_exponent(0, "mid_year") == 0.5
    assert time_exponent(0, "end_year") == 1.0
    assert time_exponent(3, "mid_year") == 3.5


def test_net_discount_rate_identity():
    d, g = 0.05, 0.03
    r = net_discount_rate(d, g)
    # (1+d) should equal (1+g)(1+r)
    assert (1 + g) * (1 + r) == pytest.approx(1 + d)


def test_current_total_no_growth_no_discount(simple_plan):
    res = project(simple_plan)
    ir = res.item_results[0]
    # $100 * 2/yr * 10 yrs = 2000, regardless of growth/discount.
    assert ir.current_total == pytest.approx(2000.0)


def test_pv_matches_closed_form(simple_plan):
    res = project(simple_plan)
    ir = res.item_results[0]
    g, d = 0.032, 0.043
    base = 100.0 * 2
    exps = [y + 0.5 for y in range(10)]
    nom = base * sum((1 + g) ** m for m in exps)
    pv = base * sum(((1 + g) / (1 + d)) ** m for m in exps)
    assert ir.nominal_total == pytest.approx(nom)
    assert ir.present_value == pytest.approx(pv)


def test_crossfoot_invariant(simple_plan):
    res = project(simple_plan)
    assert sum(y.total_current for y in res.year_results) == pytest.approx(
        res.grand_total_current)
    assert sum(y.total_nominal for y in res.year_results) == pytest.approx(
        res.grand_total_nominal)
    assert sum(y.total_pv for y in res.year_results) == pytest.approx(
        res.grand_total_present_value)


def test_pv_less_than_nominal_when_discount_exceeds_growth(simple_plan):
    res = project(simple_plan)
    assert res.grand_total_present_value < res.grand_total_nominal


def test_zero_discount_pv_equals_nominal(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.discount_rate.annual_rate = 0.0
    res = project(plan)
    assert res.grand_total_present_value == pytest.approx(res.grand_total_nominal)


def test_zero_growth_nominal_equals_current(simple_plan):
    plan = copy.deepcopy(simple_plan)
    for gr in plan.growth_rates.values():
        gr.annual_rate = 0.0
    res = project(plan)
    assert res.grand_total_nominal == pytest.approx(res.grand_total_current)


def test_timing_orders_present_value(simple_plan):
    """With positive net discounting, earlier cash-flow timing -> higher PV."""
    pvs = {}
    for timing in ("begin_year", "mid_year", "end_year"):
        plan = copy.deepcopy(simple_plan)
        plan.discount_rate.timing = timing
        pvs[timing] = project(plan).grand_total_present_value
    assert pvs["begin_year"] > pvs["mid_year"] > pvs["end_year"]


# --------------------------------------------------------------------------- #
# Occurrence model
# --------------------------------------------------------------------------- #
def ages(start, n):
    return [start + i for i in range(n)]


def test_one_time_occurs_once_in_correct_year():
    item = CareItem(category="c", item="surgery", unit_cost=1000,
                    one_time=True, one_time_age=53)
    occ = occurrences_by_year(item, ages(50, 10))
    assert sum(occ) == 1
    assert occ[3] == 1  # age 53 is index 3


def test_one_time_outside_window_never_occurs():
    item = CareItem(category="c", item="surgery", unit_cost=1000,
                    one_time=True, one_time_age=80)
    occ = occurrences_by_year(item, ages(50, 10))
    assert sum(occ) == 0


def test_every_n_years_spacing():
    item = CareItem(category="c", item="wheelchair", unit_cost=2000,
                    every_n_years=5, start_age=50)
    occ = occurrences_by_year(item, ages(50, 12))
    assert [i for i, v in enumerate(occ) if v] == [0, 5, 10]


def test_frequency_active_band():
    item = CareItem(category="c", item="therapy", unit_cost=50,
                    frequency_per_year=10, start_age=52, end_age=55)
    occ = occurrences_by_year(item, ages(50, 10))
    # active ages 52,53,54 -> indices 2,3,4
    assert [i for i, v in enumerate(occ) if v] == [2, 3, 4]
    assert all(v == 10 for v in occ if v)


def _plan(items, additional_years, base_growth_rates, *, timing="mid_year",
          discount=0.0, age=50):
    from palcp.models import Claimant, DiscountRate, LifeExpectancy, Plan
    return Plan(
        claimant=Claimant(age_at_report=age),
        life_expectancy=LifeExpectancy(age_at_report=age,
                                       additional_years=additional_years),
        discount_rate=DiscountRate(annual_rate=discount, timing=timing),
        growth_rates=base_growth_rates,
        items=items,
    )


def test_partial_final_year_proration(base_growth_rates):
    item = CareItem(category="c", item="x", unit_cost=100,
                    frequency_per_year=1, growth_key="general")
    res = project(_plan([item], 3.5, base_growth_rates))
    # 3 full years (weight 1) + 1 partial (weight 0.5) = 3.5 occurrences * $100.
    assert res.item_results[0].current_total == pytest.approx(350.0)
    assert len(res.year_results) == 4
    assert res.year_results[-1].weight == pytest.approx(0.5)


def test_one_time_event_full_cost_in_partial_final_year(base_growth_rates):
    """A discrete one-time event in the partial final year is NOT prorated."""
    item = CareItem(category="c", item="surgery", unit_cost=10000,
                    one_time=True, one_time_age=52.3, growth_key="general")
    res = project(_plan([item], 2.5, base_growth_rates, age=50))
    ir = res.item_results[0]
    assert ir.current_total == pytest.approx(10000.0)  # full, not 5000
    assert ir.occurrences_total == pytest.approx(1.0)  # whole, not 0.5


def test_every_n_years_full_cost_in_partial_final_year(base_growth_rates):
    item = CareItem(category="c", item="wheelchair", unit_cost=8000,
                    every_n_years=2, start_age=50, growth_key="general")
    res = project(_plan([item], 2.5, base_growth_rates, age=50))
    ir = res.item_results[0]
    # Replacements at age 50 and 52 (the partial year), both at full cost.
    assert ir.current_total == pytest.approx(16000.0)
    assert ir.occurrences_total == pytest.approx(2.0)


def test_one_time_at_exact_terminal_age_fires(base_growth_rates):
    item = CareItem(category="c", item="surgery", unit_cost=5000,
                    one_time=True, one_time_age=52.0, growth_key="general")
    # Whole-number LE: ages_start = [50, 51], terminal age = 52.
    res = project(_plan([item], 2.0, base_growth_rates, age=50))
    assert res.item_results[0].current_total == pytest.approx(5000.0)


def test_partial_year_time_exponent_within_window(base_growth_rates):
    """The lone partial year's discount factor uses exponent offset*frac."""
    item = CareItem(category="c", item="x", unit_cost=100,
                    frequency_per_year=1, growth_key="general")
    d = 0.05
    res = project(_plan([item], 0.5, base_growth_rates, timing="mid_year",
                        discount=d))
    yr = res.year_results[0]
    assert yr.weight == pytest.approx(0.5)
    # mid_year offset 0.5 scaled by weight 0.5 -> exponent 0.25
    assert yr.discount_factor == pytest.approx(1.0 / (1.0 + d) ** 0.25)

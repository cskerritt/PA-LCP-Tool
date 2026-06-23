"""Tests for the Daubert pre-flight validator."""

from __future__ import annotations

import copy

from palcp.models import CareItem
from palcp.validate import ERROR, WARN, validate_plan


def _messages(report):
    return [f.message for f in report.findings]


def test_clean_plan_has_no_errors(simple_plan):
    report = validate_plan(simple_plan)
    assert report.ok
    assert not report.errors


def test_missing_medical_foundation_warns(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.items[0].medical_foundation = ""
    report = validate_plan(plan)
    assert any("medical foundation" in m.lower() for m in _messages(report))
    assert any(f.domain == "Medical Foundation" for f in report.warnings)


def test_zero_unit_cost_is_error(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.items[0].unit_cost = 0
    report = validate_plan(plan)
    assert not report.ok
    assert any(f.severity == ERROR for f in report.findings)


def test_unknown_growth_key_is_error(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.items[0].growth_key = "does_not_exist"
    report = validate_plan(plan)
    assert not report.ok
    assert any("growth_key" in m for m in _messages(report))


def test_cherry_picked_percentiles_warn(simple_plan):
    plan = copy.deepcopy(simple_plan)
    extra = CareItem(category="c", item="y", unit_cost=50,
                     pricing_source="MFUS", percentile=50,
                     frequency_per_year=1,
                     medical_foundation="Dr. Test")
    plan.items.append(extra)  # same source "MFUS" at 80 and 50
    report = validate_plan(plan)
    assert any("multiple percentiles" in m for m in _messages(report))


def test_inverted_age_band_is_error(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.items[0].start_age = 70
    plan.items[0].end_age = 60
    report = validate_plan(plan)
    assert not report.ok


def test_one_time_outside_window_warns(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.items[0].one_time = True
    plan.items[0].one_time_age = 200
    report = validate_plan(plan)
    assert any("will not occur" in m for m in _messages(report))


def test_real_basis_emits_info(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.discount_rate.basis = "real"
    report = validate_plan(plan)
    assert any(f.severity == "INFO" and "real" in f.message.lower()
               for f in report.findings)


def test_no_timing_pattern_warns(simple_plan):
    plan = copy.deepcopy(simple_plan)
    plan.items[0].frequency_per_year = None
    report = validate_plan(plan)
    assert any("timing pattern" in m for m in _messages(report))

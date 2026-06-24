"""Bridge between the web app's database models and the ``palcp`` engine.

These helpers translate a stored :class:`~palcp_web.models.Case` into the
engine's dataclasses, resolve pricing, validate, project, and render the Excel
workbook -- reusing exactly the Daubert-oriented logic the CLI uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from palcp.pricing.va import SEED_PATH, load_va_outpatient

from palcp import (
    CareItem,
    Claimant,
    DiscountRate,
    GrowthRate,
    LifeExpectancy,
    Plan,
    PriceRecord,
    PricingTable,
    ValidationReport,
    __version__,
    apply_pricing,
    build_workbook,
    project,
    validate_plan,
)
from palcp.config import DEFAULT_GROWTH_KEYS, default_growth_rates
from palcp.economics.projection import ProjectionResult

from .models import Case, CaseGrowthRate, CareItemRow, PriceRecordRow
from .models import PricingTable as PricingTableRow

# Canonical growth-series keys, in display order (single source of truth shared
# by the cases and items routers and their templates).
GROWTH_KEYS = list(DEFAULT_GROWTH_KEYS.keys())

VA_DEFAULT_VERSION = "v5.26"
VA_DEFAULT_EFFECTIVE = "2026-01-01"


def _va_source_path() -> Path:
    """Prefer a normalized official CSV if present (gitignored), else the seed."""
    official = Path("data/va_charges_normalized.csv")  # produced by fetch script
    return official if official.exists() else SEED_PATH


def ensure_default_va_library(db: Session) -> PricingTableRow:
    """Create or return the system-wide default VA pricing library (idempotent)."""
    existing = db.scalar(
        select(PricingTableRow).where(PricingTableRow.is_system.is_(True))
        .order_by(PricingTableRow.id.desc()))
    if existing is not None and existing.records:
        return existing

    src = _va_source_path()
    loaded = load_va_outpatient(src, version=VA_DEFAULT_VERSION,
                                effective_date=VA_DEFAULT_EFFECTIVE)
    label = "VA Reasonable Charges " + VA_DEFAULT_VERSION
    if loaded.records and "SAMPLE" in (loaded.records[0].source or ""):
        label += " (SAMPLE — load official data)"
    table = existing or PricingTableRow(
        user_id=None, is_system=True, name=label,
        version=VA_DEFAULT_VERSION, effective_date=VA_DEFAULT_EFFECTIVE,
        description="Auto-loaded default. Public VA outpatient/professional "
                    "reasonable charges.")
    if existing is None:
        db.add(table)
        db.flush()
    for r in loaded.records:
        db.add(PriceRecordRow(
            table_id=table.id, source=r.source, code=r.code, code_type=r.code_type,
            description=r.description, amount=r.amount, percentile=r.percentile,
            geographic_area=r.geographic_area, effective_date=r.effective_date,
            citation_url=r.citation_url))
    db.commit()
    return table


def seed_growth_rate_rows(case: Case) -> list[CaseGrowthRate]:
    """Return placeholder growth-rate rows for a brand-new case."""
    rows = []
    for key, gr in default_growth_rates().items():
        rows.append(CaseGrowthRate(
            key=key, label=gr.label, annual_rate=gr.annual_rate,
            source=gr.source, citation_url=gr.citation_url, as_of=gr.as_of,
            note=gr.note,
        ))
    return rows


def _growth_rates_for(case: Case) -> dict[str, GrowthRate]:
    rates = default_growth_rates()  # ensures every default key exists
    for row in case.growth_rates:
        rates[row.key] = GrowthRate(
            key=row.key,
            label=row.label or DEFAULT_GROWTH_KEYS.get(row.key, row.key),
            annual_rate=row.annual_rate,
            source=row.source,
            citation_url=row.citation_url,
            as_of=row.as_of,
            note=row.note,
        )
    return rates


def _care_item(row: CareItemRow, geo_zip3: str = "") -> CareItem:
    return CareItem(
        category=row.category or "Uncategorized",
        item=row.item,
        unit_cost=row.unit_cost or 0.0,
        description=row.description,
        code=row.code,
        code_type=row.code_type,
        pricing_source=row.pricing_source,
        percentile=row.percentile,
        geographic_basis=row.geographic_basis or geo_zip3,
        retrieval_date=row.retrieval_date,
        units_per_occurrence=row.units_per_occurrence or 1.0,
        frequency_per_year=row.frequency_per_year,
        every_n_years=row.every_n_years,
        one_time=bool(row.one_time),
        one_time_age=row.one_time_age,
        start_age=row.start_age,
        end_age=row.end_age,
        growth_key=row.growth_key or "medical_services",
        medical_foundation=row.medical_foundation,
        notes=row.notes,
    )


def plan_from_case(case: Case) -> Plan:
    """Build a :class:`palcp.Plan` from a stored case (does not apply pricing)."""
    claimant = Claimant(
        name=case.claimant_name, dob=case.claimant_dob,
        sex=case.claimant_sex or "total", age_at_report=case.age_at_report,
        residence=case.residence,
    )
    le = LifeExpectancy(
        age_at_report=case.age_at_report if case.age_at_report is not None else 0.0,
        additional_years=case.le_additional_years or 0.0,
        source=case.le_source, citation_url=case.le_citation_url,
        as_of=case.le_as_of, note=case.le_note,
    )
    discount = DiscountRate(
        annual_rate=case.discount_rate or 0.0,
        basis=case.discount_basis or "nominal",
        timing=case.discount_timing or "mid_year",
        source=case.discount_source, citation_url=case.discount_citation_url,
        as_of=case.discount_as_of,
    )
    return Plan(
        claimant=claimant,
        life_expectancy=le,
        discount_rate=discount,
        growth_rates=_growth_rates_for(case),
        items=[_care_item(r, case.geo_zip3) for r in case.items],
        report_date=case.report_date,
        base_year=case.base_year,
        evaluator=case.evaluator,
        evaluator_credentials=case.evaluator_credentials,
        jurisdiction=case.jurisdiction,
        matter=case.name,
        percentile_policy=case.percentile_policy or 80.0,
        collateral_source_note=case.collateral_source_note,
    )


def pricing_table_from_case(case: Case) -> PricingTable:
    """Build a combined :class:`palcp.PricingTable` from the case's linked tables."""
    table = PricingTable()
    for link in case.pricing_links:
        pt = link.pricing_table
        if pt is None:
            continue
        for r in pt.records:
            table.add(PriceRecord(
                source=r.source or pt.name,
                code=r.code,
                amount=r.amount,
                code_type=r.code_type,
                description=r.description,
                percentile=r.percentile,
                geographic_area=r.geographic_area,
                effective_date=r.effective_date,
                citation_url=r.citation_url,
            ))
    return table


@dataclass
class CaseComputation:
    plan: Plan
    validation: ValidationReport
    result: ProjectionResult


def compute_case(case: Case) -> CaseComputation:
    """Resolve pricing, validate, and project a case (no workbook)."""
    plan = plan_from_case(case)
    table = pricing_table_from_case(case)
    if len(table):
        apply_pricing(plan.items, table)
    validation = validate_plan(plan)
    result = project(plan)
    return CaseComputation(plan=plan, validation=validation, result=result)


def build_case_workbook_bytes(case: Case, generated_on: str) -> tuple[bytes, CaseComputation]:
    """Generate the Excel workbook for a case and return (bytes, computation)."""
    import io

    comp = compute_case(case)
    wb = build_workbook(comp.result, comp.validation, version=__version__,
                        generated_on=generated_on)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), comp

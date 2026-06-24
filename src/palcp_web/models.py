"""Database models for the PA-LCP-Tool web app.

Multi-user: every top-level row is scoped to a ``user_id``. Cases carry their
economic assumptions inline (claimant, life expectancy, discount rate) plus a
set of per-case growth-rate rows; pricing data and rate sets live in reusable
libraries that can be applied to a case (copied in, so the case keeps a
defensible snapshot of what it actually used).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    credentials: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    cases: Mapped[list["Case"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    pricing_tables: Mapped[list["PricingTable"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    rate_libraries: Mapped[list["RateLibrary"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


# --------------------------------------------------------------------------- #
# Cases (a single life care plan)
# --------------------------------------------------------------------------- #
class Case(Base, TimestampMixin):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Report / matter metadata
    name: Mapped[str] = mapped_column(String(255))  # caption / case name
    jurisdiction: Mapped[str] = mapped_column(String(255), default="")
    evaluator: Mapped[str] = mapped_column(String(255), default="")
    evaluator_credentials: Mapped[str] = mapped_column(String(255), default="")
    report_date: Mapped[str] = mapped_column(String(32), default="")
    base_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentile_policy: Mapped[float] = mapped_column(Float, default=80.0)
    collateral_source_note: Mapped[str] = mapped_column(Text, default="")

    # Claimant
    claimant_name: Mapped[str] = mapped_column(String(255), default="")
    claimant_dob: Mapped[str] = mapped_column(String(32), default="")
    claimant_sex: Mapped[str] = mapped_column(String(16), default="total")
    age_at_report: Mapped[float | None] = mapped_column(Float, nullable=True)
    residence: Mapped[str] = mapped_column(String(255), default="")
    geo_zip3: Mapped[str] = mapped_column(String(3), default="")
    geo_locality_name: Mapped[str] = mapped_column(String(128), default="")

    # Life expectancy
    le_additional_years: Mapped[float] = mapped_column(Float, default=0.0)
    le_source: Mapped[str] = mapped_column(String(512), default="")
    le_citation_url: Mapped[str] = mapped_column(String(512), default="")
    le_as_of: Mapped[str] = mapped_column(String(64), default="")
    le_note: Mapped[str] = mapped_column(Text, default="")

    # Discount rate
    discount_rate: Mapped[float] = mapped_column(Float, default=0.0)
    discount_basis: Mapped[str] = mapped_column(String(16), default="nominal")
    discount_timing: Mapped[str] = mapped_column(String(16), default="mid_year")
    discount_source: Mapped[str] = mapped_column(String(512), default="")
    discount_citation_url: Mapped[str] = mapped_column(String(512), default="")
    discount_as_of: Mapped[str] = mapped_column(String(64), default="")

    user: Mapped["User"] = relationship(back_populates="cases")
    items: Mapped[list["CareItemRow"]] = relationship(
        back_populates="case", cascade="all, delete-orphan",
        order_by="CareItemRow.sort_order")
    growth_rates: Mapped[list["CaseGrowthRate"]] = relationship(
        back_populates="case", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(
        back_populates="case", cascade="all, delete-orphan",
        order_by="Report.created_at.desc()")
    pricing_links: Mapped[list["CasePricingLink"]] = relationship(
        back_populates="case", cascade="all, delete-orphan")


class CaseGrowthRate(Base):
    __tablename__ = "case_growth_rates"
    __table_args__ = (UniqueConstraint("case_id", "key", name="uq_case_growth_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(255), default="")
    annual_rate: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(512), default="")
    citation_url: Mapped[str] = mapped_column(String(512), default="")
    as_of: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")

    case: Mapped["Case"] = relationship(back_populates="growth_rates")


class CareItemRow(Base, TimestampMixin):
    __tablename__ = "care_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[str] = mapped_column(String(128), default="Uncategorized")
    item: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str] = mapped_column(String(64), default="")
    code_type: Mapped[str] = mapped_column(String(32), default="")
    pricing_source: Mapped[str] = mapped_column(String(255), default="")
    percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    geographic_basis: Mapped[str] = mapped_column(String(255), default="")
    retrieval_date: Mapped[str] = mapped_column(String(64), default="")
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    units_per_occurrence: Mapped[float] = mapped_column(Float, default=1.0)
    frequency_per_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    every_n_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    one_time: Mapped[bool] = mapped_column(Boolean, default=False)
    one_time_age: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_age: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_age: Mapped[float | None] = mapped_column(Float, nullable=True)
    growth_key: Mapped[str] = mapped_column(String(64), default="medical_services")
    medical_foundation: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    case: Mapped["Case"] = relationship(back_populates="items")


# --------------------------------------------------------------------------- #
# Pricing libraries
# --------------------------------------------------------------------------- #
class PricingTable(Base, TimestampMixin):
    __tablename__ = "pricing_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[str] = mapped_column(String(32), default="")
    effective_date: Mapped[str] = mapped_column(String(32), default="")

    user: Mapped["User"] = relationship(back_populates="pricing_tables")
    records: Mapped[list["PriceRecordRow"]] = relationship(
        back_populates="table", cascade="all, delete-orphan")
    case_links: Mapped[list["CasePricingLink"]] = relationship(
        back_populates="pricing_table", cascade="all, delete-orphan")


class PriceRecordRow(Base):
    __tablename__ = "price_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_tables.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(255), default="")
    code: Mapped[str] = mapped_column(String(64), index=True)
    code_type: Mapped[str] = mapped_column(String(32), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    geographic_area: Mapped[str] = mapped_column(String(255), default="")
    effective_date: Mapped[str] = mapped_column(String(64), default="")
    citation_url: Mapped[str] = mapped_column(String(512), default="")

    table: Mapped["PricingTable"] = relationship(back_populates="records")


class CasePricingLink(Base):
    __tablename__ = "case_pricing_links"
    __table_args__ = (
        UniqueConstraint("case_id", "pricing_table_id", name="uq_case_pricing"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    pricing_table_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_tables.id", ondelete="CASCADE"), index=True)

    case: Mapped["Case"] = relationship(back_populates="pricing_links")
    pricing_table: Mapped["PricingTable"] = relationship(back_populates="case_links")


# --------------------------------------------------------------------------- #
# Reusable growth-rate (assumption) libraries
# --------------------------------------------------------------------------- #
class RateLibrary(Base, TimestampMixin):
    __tablename__ = "rate_libraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")

    user: Mapped["User"] = relationship(back_populates="rate_libraries")
    entries: Mapped[list["RateLibraryEntry"]] = relationship(
        back_populates="library", cascade="all, delete-orphan")


class RateLibraryEntry(Base):
    __tablename__ = "rate_library_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("rate_libraries.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(255), default="")
    annual_rate: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(512), default="")
    citation_url: Mapped[str] = mapped_column(String(512), default="")
    as_of: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")

    library: Mapped["RateLibrary"] = relationship(back_populates="entries")


# --------------------------------------------------------------------------- #
# Generated reports
# --------------------------------------------------------------------------- #
class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow)
    generated_on: Mapped[str] = mapped_column(String(32), default="")
    filename: Mapped[str] = mapped_column(String(255), default="report.xlsx")

    total_current: Mapped[float] = mapped_column(Float, default=0.0)
    total_nominal: Mapped[float] = mapped_column(Float, default=0.0)
    total_present_value: Mapped[float] = mapped_column(Float, default=0.0)
    validation_summary: Mapped[str] = mapped_column(String(255), default="")

    workbook: Mapped[bytes] = mapped_column(LargeBinary)

    case: Mapped["Case"] = relationship(back_populates="reports")


# --------------------------------------------------------------------------- #
# Edit history / audit log
# --------------------------------------------------------------------------- #
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow)
    entity: Mapped[str] = mapped_column(String(64))  # "case", "item", ...
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32))  # "create"|"update"|"delete"
    summary: Mapped[str] = mapped_column(Text, default="")

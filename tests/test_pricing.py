"""Tests for pricing schema, loaders, and lookup."""

from __future__ import annotations

import pytest

from palcp.models import CareItem
from palcp.pricing import PriceRecord, PricingTable, apply_pricing, load_pricing, resolve_item


def test_pricing_table_lookup_normalizes_code():
    t = PricingTable(records=[PriceRecord(source="S", code="k0005", amount=2480)])
    assert t.by_code("K0005")[0].amount == 2480
    assert t.by_code(" k0005 ")[0].amount == 2480


def test_resolve_direct_cost_wins():
    item = CareItem(category="c", item="x", unit_cost=212, code="99214")
    t = PricingTable(records=[PriceRecord(source="S", code="99214", amount=198)])
    res = resolve_item(item, t)
    assert res.method == "direct"
    assert res.unit_cost == 212


def test_resolve_matched_from_table():
    item = CareItem(category="c", item="x", unit_cost=0, code="72148")
    t = PricingTable(records=[PriceRecord(source="VA", code="72148", amount=1185,
                                          effective_date="2026")])
    res = resolve_item(item, t)
    assert res.method == "matched"
    assert res.unit_cost == 1185


def test_resolve_unresolved():
    item = CareItem(category="c", item="x", unit_cost=0, code="NOPE")
    res = resolve_item(item, PricingTable())
    assert res.method == "unresolved"
    assert res.unit_cost == 0.0


def test_resolve_prefers_source_and_percentile_match():
    item = CareItem(category="c", item="x", unit_cost=0, code="99214",
                    pricing_source="MFUS", percentile=80)
    t = PricingTable(records=[
        PriceRecord(source="VA", code="99214", amount=198),
        PriceRecord(source="MFUS", code="99214", amount=240, percentile=80),
        PriceRecord(source="MFUS", code="99214", amount=210, percentile=50),
    ])
    res = resolve_item(item, t)
    assert res.record.source == "MFUS"
    assert res.record.percentile == 80
    assert res.unit_cost == 240


def test_apply_pricing_backfills_metadata():
    item = CareItem(category="c", item="x", unit_cost=0, code="K0005")
    t = PricingTable(records=[PriceRecord(source="CMS DMEPOS", code="K0005",
                                          amount=2480, code_type="HCPCS",
                                          geographic_area="PA",
                                          effective_date="2026")])
    apply_pricing([item], t)
    assert item.unit_cost == 2480
    assert item.pricing_source == "CMS DMEPOS"
    assert item.code_type == "HCPCS"
    assert item.geographic_basis == "PA"
    assert item.retrieval_date == "2026"


def test_load_pricing_csv(tmp_path):
    p = tmp_path / "pricing.csv"
    p.write_text(
        "source,code,code_type,description,amount,percentile,geographic_area,"
        "effective_date,citation_url\n"
        "VA,72148,CPT,MRI,1185,,National,2026,http://x\n",
        encoding="utf-8",
    )
    table = load_pricing(p)
    assert len(table) == 1
    assert table.by_code("72148")[0].amount == 1185


def test_load_pricing_with_column_map(tmp_path):
    p = tmp_path / "vendor.csv"
    p.write_text("CPT/HCPCS,Description,Charge\n99214,Office visit,198\n",
                 encoding="utf-8")
    table = load_pricing(p, preset="va_reasonable_charges")
    rec = table.by_code("99214")[0]
    assert rec.amount == 198
    assert rec.source == "VA Reasonable Charges"
    assert rec.code_type == "CPT/HCPCS"


def test_load_pricing_strips_currency(tmp_path):
    p = tmp_path / "pricing.csv"
    p.write_text("source,code,amount\nS,X1,\"$1,185.50\"\n", encoding="utf-8")
    table = load_pricing(p)
    assert table.by_code("X1")[0].amount == pytest.approx(1185.50)


def test_load_pricing_missing_required_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pricing(p)


def test_load_pricing_tolerates_messy_cells(tmp_path):
    """Non-numeric amounts are skipped; '%' and space separators parse."""
    p = tmp_path / "messy.csv"
    p.write_text(
        "source,code,amount,percentile\n"
        "S,A1,N/A,80%\n"            # non-numeric amount -> row skipped
        "S,A2,\"1 200\",80%\n"       # space thousands sep + percent
        "S,A3,by report,\n",        # non-numeric amount -> row skipped
        encoding="utf-8",
    )
    table = load_pricing(p)  # must not raise
    assert len(table) == 1
    rec = table.by_code("A2")[0]
    assert rec.amount == pytest.approx(1200.0)
    assert rec.percentile == pytest.approx(80.0)

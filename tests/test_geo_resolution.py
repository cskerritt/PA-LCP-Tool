from palcp.models import CareItem
from palcp.pricing import PriceRecord, PricingTable
from palcp.pricing.lookup import resolve_item


def _table():
    return PricingTable(records=[
        PriceRecord(source="VA v5.26", code="99214", amount=210.0, code_type="CPT",
                    geographic_area="191", effective_date="2026-01-01"),
        PriceRecord(source="VA v5.26", code="99214", amount=190.0, code_type="CPT",
                    geographic_area="National", effective_date="2026-01-01"),
    ])


def test_prefers_zip3_locality_match():
    item = CareItem(category="", item="Visit", unit_cost=0.0, code="99214",
                    geographic_basis="191")
    res = resolve_item(item, _table())
    assert res.unit_cost == 210.0
    assert res.record.geographic_area == "191"


def test_falls_back_to_national_when_no_locality_match():
    item = CareItem(category="", item="Visit", unit_cost=0.0, code="99214",
                    geographic_basis="999")  # no 999 locality in table
    res = resolve_item(item, _table())
    assert res.unit_cost == 190.0
    assert res.record.geographic_area == "National"


def test_unmatched_code_is_unresolved_not_guessed():
    item = CareItem(category="", item="X", unit_cost=0.0, code="00000",
                    geographic_basis="191")
    res = resolve_item(item, _table())
    assert res.method == "unresolved"
    assert res.unit_cost == 0.0

from palcp.models import CareItem
from palcp.pricing import PriceRecord, PricingTable, apply_pricing


def _table():
    return PricingTable(records=[
        PriceRecord(source="VA Reasonable Charges v5.26", code="99214",
                    amount=198.0, code_type="CPT",
                    description="Office/outpatient visit, established patient",
                    percentile=None, geographic_area="191",
                    effective_date="2026-01-01",
                    citation_url="https://www.va.gov/x"),
    ])


def test_apply_pricing_fills_blank_desc_category_growth():
    item = CareItem(category="Uncategorized", item="Follow-up", unit_cost=0.0,
                    code="99214")
    res = apply_pricing([item], _table())[0]
    assert res.method == "matched"
    assert item.unit_cost == 198.0
    assert item.description == "Office/outpatient visit, established patient"
    assert item.category == "Physician Services"      # from category_hint
    assert item.growth_key == "medical_services"       # from growth_map
    assert item.pricing_source == "VA Reasonable Charges v5.26"


def test_apply_pricing_does_not_overwrite_user_values():
    item = CareItem(category="My Category", item="Visit", unit_cost=0.0,
                    code="99214", description="my desc", growth_key="general")
    apply_pricing([item], _table())
    assert item.description == "my desc"
    assert item.category == "My Category"
    assert item.growth_key == "general"

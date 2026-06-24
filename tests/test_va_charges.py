from palcp.pricing.va_charges import VADataset, VAChargeBasis, compute_charge


def _ds():
    return VADataset(
        version="v5.26", effective_date="2026-01-01",
        bases={
            "99214": [VAChargeBasis(
                code="99214", table="G", charge_type="Physician/Professional",
                description="Office/outpatient visit, established",
                charge=None, work_rvu=1.92, facility_pe_rvu=1.5,
                nonfacility_pe_rvu=1.8, total_expense_rvu=None,
                cf_category="Office/Home/Urgent Care Visits", gaaf_table="L",
                gaaf_category="Office/Home/Urgent Care Visits",
                methodology="RBRVS", status_indicator="")],
            "72148": [VAChargeBasis(
                code="72148", table="F", charge_type="Outpatient Facility",
                description="MRI lumbar spine w/o dye", charge=1627.17,
                work_rvu=None, facility_pe_rvu=None, nonfacility_pe_rvu=None,
                total_expense_rvu=None, cf_category=None, gaaf_table="P",
                gaaf_category=None, methodology="FAIR Health", status_indicator="")],
            "K0005": [VAChargeBasis(
                code="K0005", table="K", charge_type="DME",
                description="Ultralightweight wheelchair", charge=4705.80,
                work_rvu=None, facility_pe_rvu=None, nonfacility_pe_rvu=None,
                total_expense_rvu=None, cf_category=None, gaaf_table="Q",
                gaaf_category="Non-Drug", methodology="", status_indicator="")],
        },
        cf={"Office/Home/Urgent Care Visits": 101.17},
        gaaf={
            ("L", "191", "Office/Home/Urgent Care Visits"): 0.95,
            ("P", "191", None): 1.26,
            ("Q", "191", "Non-Drug"): 1.10,
        },
        modifier={"50": 1.5},
    )


def test_direct_charge_outpatient_facility():
    (c,) = compute_charge(_ds(), "72148", "191")
    assert c.table == "F"
    assert c.national == 1627.17
    assert c.gaaf == 1.26
    assert c.amount == 2050.23          # 1627.17 * 1.26


def test_direct_charge_dme():
    (c,) = compute_charge(_ds(), "K0005", "191")
    assert c.amount == 5176.38          # 4705.80 * 1.10


def test_professional_non_facility_default():
    (c,) = compute_charge(_ds(), "99214", "191")
    assert c.setting == "non_facility"
    assert c.national == 376.35         # (1.92 + 1.80) * 101.17
    assert c.amount == 357.53           # * 0.95


def test_professional_facility_setting():
    (c,) = compute_charge(_ds(), "99214", "191", setting="facility")
    assert c.national == 346.00         # (1.92 + 1.50) * 101.17
    assert c.amount == 328.70           # * 0.95


def test_unknown_code_returns_empty():
    assert compute_charge(_ds(), "00000", "191") == []


def test_modifier_multiplies():
    (c,) = compute_charge(_ds(), "72148", "191", modifier="50")
    assert c.amount == 3075.35          # 2050.2342 * 1.5 -> 3075.3513 -> 3075.35


def test_missing_locality_falls_back_to_national():
    (c,) = compute_charge(_ds(), "72148", "999")   # no 999 in gaaf table
    assert c.gaaf == 1.0
    assert c.amount == c.national == 1627.17
    assert "national" in c.breakdown.lower()

from pathlib import Path

import pytest

from palcp.pricing.va_charges import VAChargeBasis, VADataset, compute_charge
from palcp.pricing.va_ingest import _catkey, _num, from_sqlite, to_sqlite

VA_DIR = Path.home() / "Downloads" / "VA UCR TABLES"


def test_num_parses_currency_and_blanks():
    assert _num("$1,627.17") == 1627.17
    assert _num("Blank") is None
    assert _num("BR") is None
    assert _num(None) is None
    assert _num(2.25) == 2.25


def test_catkey_matches_across_table_label_variants():
    key = "officehomeurgentcarevisits"
    assert _catkey("Office/ Home/ Urgent Care Visits  CF GAAF") == key
    assert _catkey("Office/Home/Urgent Care Visits") == key
    assert _catkey("Surgery  CF GAAF") == "surgery"


def test_sqlite_roundtrip(tmp_path):
    ds = VADataset(version="v5.26", effective_date="2026-01-01",
                   bases={"99214": [VAChargeBasis(
                       code="99214", table="G", charge_type="Physician/Professional",
                       description="Office visit", work_rvu=1.92, nonfacility_pe_rvu=1.8,
                       facility_pe_rvu=1.5, cf_category="Office/Home/Urgent Care Visits",
                       gaaf_table="L", gaaf_category="Office/Home/Urgent Care Visits")]},
                   cf={"Office/Home/Urgent Care Visits": 101.17},
                   gaaf={("L", "191", "Office/Home/Urgent Care Visits"): 0.95},
                   modifier={"50": 1.5})
    p = tmp_path / "va.sqlite"
    to_sqlite(ds, p)
    ds2 = from_sqlite(p)
    assert ds2.version == "v5.26"
    (c,) = compute_charge(ds2, "99214", "191")
    assert c.amount == 357.53


@pytest.mark.skipif(not VA_DIR.exists(), reason="VA UCR TABLES not present locally")
def test_real_va_data_validates_to_the_cent():
    from palcp.pricing.va_ingest import ingest_va_tables
    ds = ingest_va_tables(VA_DIR)
    assert len(ds.bases) > 10000
    assert len(ds.gaaf) > 5000

    def amounts(code, table, **kw):
        return [c.amount for c in compute_charge(ds, code, "191", **kw)
                if c.table == table]

    assert 2050.23 in amounts("72148", "F")            # MRI, outpatient facility
    assert 357.53 in amounts("99214", "G")             # office visit, non-facility
    assert 5176.38 in amounts("K0005", "K")            # wheelchair, DME
    assert 71.86 in amounts("97110", "G")              # PT, physical medicine

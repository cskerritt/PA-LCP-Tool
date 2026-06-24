"""Web tests for VA-UCR default pricing + preload features (SQLite-backed)."""

from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(
    suffix=".db", delete=False).name
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SESSION_HTTPS_ONLY"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from palcp_web.db import init_db  # noqa: E402
from palcp_web.main import app  # noqa: E402

init_db()


def _register(c: TestClient, email: str) -> None:
    r = c.post("/register", data={"email": email, "password": "password1",
                                  "full_name": "Eval", "credentials": "CLCP"})
    assert r.status_code == 200


def _make_case(c: TestClient, name: str = "VA Case") -> int:
    r = c.post("/cases", data={"name": name})
    return int(str(r.url).rstrip("/").split("/")[-1])


def test_models_have_new_columns():
    from palcp_web.models import Case, PricingTable
    assert hasattr(Case, "geo_zip3")
    assert hasattr(Case, "geo_locality_name")
    assert hasattr(PricingTable, "is_system")
    assert hasattr(PricingTable, "version")
    assert hasattr(PricingTable, "effective_date")


def test_default_va_library_seeded_and_autolinked():
    from palcp_web.db import SessionLocal
    from palcp_web.services import ensure_default_va_library
    from palcp_web.models import PricingTable, CasePricingLink
    db = SessionLocal()
    table = ensure_default_va_library(db)
    assert table.is_system is True
    assert "VA Reasonable Charges" in table.name
    assert len(table.records) >= 4          # from the SAMPLE seed
    db.close()

    c = TestClient(app)
    _register(c, "va@example.com")
    cid = _make_case(c, "Autolink Case")
    db = SessionLocal()
    links = db.query(CasePricingLink).filter(CasePricingLink.case_id == cid).all()
    linked_tables = [db.get(PricingTable, l.pricing_table_id) for l in links]
    assert any(t.is_system for t in linked_tables)   # VA auto-linked
    db.close()


def test_lookup_code_autofills_from_va():
    c = TestClient(app)
    _register(c, "lookup@example.com")
    cid = _make_case(c, "Lookup Case")
    c.post(f"/cases/{cid}", data={"name": "Lookup Case", "age_at_report": "40",
                                  "le_additional_years": "30", "geo_zip3": "191"})
    res = c.get(f"/cases/{cid}/lookup-code", params={"code": "99214"})
    assert res.status_code == 200
    body = res.text
    assert 'name="unit_cost"' in body and "200" in body   # SAMPLE price
    assert "Office/outpatient visit" in body               # description
    assert "medical_services" in body                      # growth key
    assert "VA Reasonable Charges" in body                 # source


def test_case_zip3_persists():
    from palcp_web.db import SessionLocal
    from palcp_web.models import Case
    c = TestClient(app)
    _register(c, "zip@example.com")
    cid = _make_case(c, "Zip Case")
    c.post(f"/cases/{cid}", data={"name": "Zip Case", "age_at_report": "40",
                                  "le_additional_years": "30", "geo_zip3": "19103",
                                  "geo_locality_name": "Philadelphia"})
    db = SessionLocal()
    case = db.get(Case, cid)
    assert case.geo_zip3 == "191"            # truncated to 3 digits
    assert case.geo_locality_name == "Philadelphia"
    db.close()


def test_lookup_unknown_code_reports_no_match():
    c = TestClient(app)
    _register(c, "lookup2@example.com")
    cid = _make_case(c, "Lookup2")
    res = c.get(f"/cases/{cid}/lookup-code", params={"code": "00000"})
    assert res.status_code == 200
    assert "No VA match" in res.text


def test_catalog_add_creates_priced_row():
    c = TestClient(app)
    _register(c, "cat@example.com")
    cid = _make_case(c, "Cat Case")
    c.post(f"/cases/{cid}", data={"name": "Cat Case", "age_at_report": "40",
                                  "le_additional_years": "30", "geo_zip3": "191"})
    assert "Physiatry" in c.get(f"/cases/{cid}/catalog").text
    r = c.post(f"/cases/{cid}/catalog/add", data={"key": "pmr_followup"},
               follow_redirects=True)
    assert r.status_code == 200
    detail = c.get(f"/cases/{cid}").text
    assert "99214" in detail                       # code carried in
    assert "200.00" in detail                      # auto-priced from VA SAMPLE


def test_zzz_default_library_reloads_when_official_appears(tmp_path, monkeypatch):
    # Named to sort last: it swaps the shared system table to "official" data.
    from palcp_web import services
    from palcp_web.db import SessionLocal
    db = SessionLocal()
    sample = services.ensure_default_va_library(db)
    assert "SAMPLE" in sample.name           # starts as the labeled seed
    db.close()

    official = tmp_path / "official.csv"
    official.write_text(
        "source,code,code_type,description,amount,percentile,geographic_area,"
        "effective_date,citation_url\n"
        "VA Reasonable Charges v5.26,99214,CPT,Office visit,250,,191,2026-01-01,"
        "https://www.va.gov/x\n", encoding="utf-8")
    monkeypatch.setattr(services, "_va_source_path", lambda: official)

    db = SessionLocal()
    reloaded = services.ensure_default_va_library(db)
    assert "SAMPLE" not in reloaded.name     # upgraded to official label
    assert any(r.amount == 250.0 for r in reloaded.records)
    db.close()

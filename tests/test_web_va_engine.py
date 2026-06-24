"""Web integration of the VA charge engine (localized, per-item setting)."""

from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(
    suffix=".db", delete=False).name
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SESSION_HTTPS_ONLY"] = "0"
os.environ["PALCP_VA_DATASET"] = ""  # we inject a fixture dataset instead

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from palcp_web import va_pricing  # noqa: E402
from palcp_web.db import init_db  # noqa: E402
from palcp_web.main import app  # noqa: E402
from palcp.pricing.va_charges import VAChargeBasis, VADataset  # noqa: E402

init_db()


def _fixture_ds() -> VADataset:
    return VADataset(
        version="v5.26", effective_date="2026-01-01",
        bases={
            "99214": [
                VAChargeBasis(code="99214", table="G",
                              charge_type="Physician/Professional",
                              description="Office visit, established",
                              work_rvu=1.92, facility_pe_rvu=1.5,
                              nonfacility_pe_rvu=1.8,
                              cf_category="Office/Home/Urgent Care Visits",
                              gaaf_table="L",
                              gaaf_category="Office/Home/Urgent Care Visits"),
                VAChargeBasis(code="99214", table="F",
                              charge_type="Outpatient Facility",
                              description="Office visit facility", charge=394.62,
                              gaaf_table="P", gaaf_category=None),
            ],
        },
        cf={"Office/Home/Urgent Care Visits": 101.17},
        gaaf={("L", "191", "Office/Home/Urgent Care Visits"): 0.95,
              ("P", "191", None): 1.26},
    )


@pytest.fixture(autouse=True)
def _inject_dataset(monkeypatch):
    monkeypatch.setattr(va_pricing, "get_va_dataset", _fixture_ds)


def _register(c, email):
    assert c.post("/register", data={"email": email, "password": "password1",
                                     "full_name": "E", "credentials": "C"}).status_code == 200


def _case_zip(c, zip3="191"):
    cid = int(str(c.post("/cases", data={"name": "C"}).url).rstrip("/").split("/")[-1])
    c.post(f"/cases/{cid}", data={"name": "C", "age_at_report": "40",
                                  "le_additional_years": "30", "geo_zip3": zip3})
    return cid


def test_item_priced_from_va_engine_non_facility():
    c = TestClient(app)
    _register(c, "eng1@x.com")
    cid = _case_zip(c)
    c.post(f"/cases/{cid}/items", data={"item": "Visit", "code": "99214",
                                        "frequency_per_year": "4"})
    detail = c.get(f"/cases/{cid}").text
    assert "357.53" in detail          # (1.92+1.8) * 101.17 * 0.95


def test_item_facility_setting_changes_charge():
    c = TestClient(app)
    _register(c, "eng2@x.com")
    cid = _case_zip(c)
    c.post(f"/cases/{cid}/items", data={"item": "Visit", "code": "99214",
                                        "frequency_per_year": "4",
                                        "va_setting": "facility"})
    detail = c.get(f"/cases/{cid}").text
    assert "328.70" in detail          # (1.92+1.5) * 101.17 * 0.95


def test_lookup_shows_localized_charge_and_combinations():
    c = TestClient(app)
    _register(c, "eng3@x.com")
    cid = _case_zip(c)
    body = c.get(f"/cases/{cid}/lookup-code", params={"code": "99214"}).text
    assert "357.53" in body                          # professional (best) auto-fill
    assert "Outpatient Facility" in body             # the other combination shown
    assert "497.22" in body                          # 394.62 * 1.26 facility charge

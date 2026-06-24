"""End-to-end tests for the FastAPI web app (SQLite-backed)."""

from __future__ import annotations

import os
import re
import tempfile

import pytest

# Configure the app BEFORE importing it (settings are read at import time).
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(
    suffix=".db", delete=False).name
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SESSION_HTTPS_ONLY"] = "0"  # allow cookies over the test client's http
os.environ["PALCP_VA_DATASET"] = ""  # hermetic: no VA dataset in unit tests

from fastapi.testclient import TestClient  # noqa: E402

from palcp_web.db import init_db  # noqa: E402
from palcp_web.main import app  # noqa: E402

init_db()


def _client() -> TestClient:
    return TestClient(app)


def _register(c: TestClient, email: str, password: str = "password1") -> None:
    r = c.post("/register", data={"email": email, "password": password,
                                  "full_name": "Eval", "credentials": "CLCP"})
    assert r.status_code == 200


def _make_case(c: TestClient, name: str = "Doe v. Roe") -> str:
    r = c.post("/cases", data={"name": name})
    assert r.status_code == 200
    return str(r.url).rstrip("/").split("/")[-1]


def _set_assumptions(c: TestClient, cid: str) -> None:
    r = c.post(f"/cases/{cid}", data={
        "name": "Doe v. Roe", "age_at_report": "42", "le_additional_years": "38",
        "discount_rate": "0.043", "discount_basis": "nominal",
        "discount_timing": "mid_year", "le_source": "CDC test",
        "discount_source": "Treasury test",
        "gr_medical_services_rate": "0.032", "gr_medical_services_source": "BLS test",
    })
    assert r.status_code == 200


def test_db_url_normalization():
    from palcp_web.config import _normalize_db_url
    assert (_normalize_db_url("postgres://u:p@h:5432/d")
            == "postgresql+psycopg://u:p@h:5432/d")
    assert (_normalize_db_url("postgresql://u:p@h/d")
            == "postgresql+psycopg://u:p@h/d")
    assert _normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"
    assert (_normalize_db_url("postgresql+psycopg://x")  # already qualified
            == "postgresql+psycopg://x")


def test_health():
    assert _client().get("/health").json()["status"] == "ok"


def test_requires_login():
    c = _client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_register_login_logout():
    c = _client()
    _register(c, "flow@example.com")
    assert "New case" in c.get("/").text  # logged in
    assert c.post("/logout").status_code == 200
    assert c.get("/", follow_redirects=False).status_code == 303


def test_full_case_to_report_flow():
    c = _client()
    _register(c, "report@example.com")
    cid = _make_case(c)
    _set_assumptions(c, cid)
    r = c.post(f"/cases/{cid}/items", data={
        "category": "Physician Services", "item": "Physiatry follow-up",
        "unit_cost": "212", "frequency_per_year": "4",
        "growth_key": "medical_services", "medical_foundation": "Dr X 2026"},
        headers={"HX-Request": "true"})
    assert r.status_code == 200 and "Physiatry" in r.text

    assert c.post(f"/cases/{cid}/report").status_code == 200
    rid = re.search(r"/reports/(\d+)/download", c.get(f"/cases/{cid}").text).group(1)
    dl = c.get(f"/reports/{rid}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/vnd.openxml")
    assert dl.content[:2] == b"PK"  # valid xlsx (zip) magic


def test_multi_user_isolation():
    a = _client()
    _register(a, "owner@example.com")
    cid = _make_case(a, "Private case")

    b = _client()
    _register(b, "intruder@example.com")
    # User B must not see user A's case.
    assert b.get(f"/cases/{cid}", follow_redirects=False).status_code == 404
    # ...and B's own dashboard does not list A's case.
    assert "Private case" not in b.get("/").text
    # A still sees it.
    assert "Private case" in a.get(f"/cases/{cid}").text


def test_pricing_table_resolves_item_by_code():
    c = _client()
    _register(c, "pricing@example.com")
    cid = _make_case(c)
    _set_assumptions(c, cid)

    # Create a pricing table with a code.
    csv = ("source,code,amount\nCMS DMEPOS,K0005,2480\n")
    r = c.post("/pricing",
               data={"name": "DMEPOS", "preset": ""},
               files={"file": ("p.csv", csv, "text/csv")})
    assert r.status_code == 200
    # Link it to the case.
    pid = str(r.url).rstrip("/").split("/")[-1]
    assert c.post(f"/cases/{cid}/pricing/link",
                  data={"pricing_table_id": pid}).status_code == 200

    # Add an item with no unit cost but a matching code.
    c.post(f"/cases/{cid}/items", data={
        "category": "DME", "item": "Wheelchair", "unit_cost": "0",
        "code": "K0005", "every_n_years": "5", "growth_key": "dme",
        "medical_foundation": "Dr X"}, headers={"HX-Request": "true"})

    # The detail page should now reflect the resolved $2,480 unit cost.
    body = c.get(f"/cases/{cid}").text
    assert "2,480" in body


def test_csv_item_import():
    c = _client()
    _register(c, "import@example.com")
    cid = _make_case(c)
    _set_assumptions(c, cid)
    csv = (
        "category,item,unit_cost,frequency_per_year,growth_key,medical_foundation\n"
        "Therapies,Physical therapy,165,36,medical_services,Dr X note\n"
        "Medications,Gabapentin,1080,1,rx,Dr Y note\n"
    )
    r = c.post(f"/cases/{cid}/import-items",
               files={"file": ("items.csv", csv, "text/csv")})
    assert r.status_code == 200
    body = c.get(f"/cases/{cid}").text
    assert "Physical therapy" in body and "Gabapentin" in body

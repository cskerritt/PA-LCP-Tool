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

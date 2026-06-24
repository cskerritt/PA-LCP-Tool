"""HTMX endpoint that resolves a procedure code against the case's linked VA
pricing table and returns out-of-band input swaps that preload the item form.

Nothing is persisted here; the planner reviews the auto-filled values and submits
the form. Unmatched codes return a visible 'no match' notice (never a guess)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from palcp.pricing import apply_pricing

from ..db import get_db
from ..models import CareItemRow, User
from ..security import current_user
from ..services import GROWTH_KEYS, _care_item, pricing_table_from_case
from ..templating import render_partial
from .cases import get_owned_case

router = APIRouter()


@router.get("/cases/{case_id}/lookup-code")
def lookup_code(case_id: int, request: Request, code: str, code_type: str = "",
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    table = pricing_table_from_case(case)
    probe = _care_item(CareItemRow(
        category="", item="probe", code=code, code_type=code_type,
        geographic_basis=case.geo_zip3 or "", unit_cost=0.0,
        percentile=case.percentile_policy))
    apply_pricing([probe], table)
    matched = bool(probe.unit_cost and probe.unit_cost > 0)
    return render_partial(request, "cases/_item_autofill.html",
                          matched=matched, item=probe,
                          growth_keys=GROWTH_KEYS, code=code)

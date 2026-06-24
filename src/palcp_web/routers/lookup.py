"""HTMX endpoint that resolves a procedure code to its localized VA charge and
returns out-of-band input swaps that preload the item form.

Prefers the full VA charge dataset (computed for the case's 3-digit ZIP and the
chosen care setting) and surfaces every "combination" a code has (e.g. an
outpatient-facility charge and a professional read). Falls back to the flat
SAMPLE/vendor library when the dataset is not built. Nothing is persisted; the
planner reviews the auto-filled values and submits. Unmatched codes return a
visible 'no match' notice, never a guess."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from palcp.pricing import apply_pricing
from palcp.pricing.growth_map import category_hint, growth_key_for

from .. import va_pricing
from ..db import get_db
from ..models import CareItemRow, User
from ..security import current_user
from ..services import GROWTH_KEYS, _care_item, pricing_table_from_case
from ..templating import render_partial
from .cases import get_owned_case

router = APIRouter()


@router.get("/cases/{case_id}/lookup-code")
def lookup_code(case_id: int, request: Request, code: str, code_type: str = "",
                setting: str = "non_facility", va_setting: str = "",
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    setting = va_setting or setting
    zip3 = case.geo_zip3 or ""

    combos = va_pricing.va_combinations(code, zip3, setting=setting)
    if combos:
        ds = va_pricing.get_va_dataset()
        best = min(combos, key=lambda c: 0 if c.table == "G" else 1)
        probe = _care_item(CareItemRow(
            category="", item="probe", code=code, code_type="CPT/HCPCS",
            geographic_basis=best.zip3 or zip3, unit_cost=best.amount,
            description=best.description, percentile=case.percentile_policy))
        probe.pricing_source = f"VA Reasonable Charges {ds.version}"
        probe.retrieval_date = ds.effective_date
        probe.category = category_hint(code, "CPT/HCPCS")
        probe.growth_key = growth_key_for(code, "CPT/HCPCS")
        return render_partial(request, "cases/_item_autofill.html",
                              matched=True, item=probe, combos=combos,
                              zip3=zip3, growth_keys=GROWTH_KEYS, code=code)

    # Fallback: flat pricing library (SAMPLE seed or vendor uploads).
    table = pricing_table_from_case(case)
    probe = _care_item(CareItemRow(
        category="", item="probe", code=code, code_type=code_type,
        geographic_basis=zip3, unit_cost=0.0, percentile=case.percentile_policy))
    apply_pricing([probe], table)
    matched = bool(probe.unit_cost and probe.unit_cost > 0)
    return render_partial(request, "cases/_item_autofill.html",
                          matched=matched, item=probe, combos=[],
                          zip3=zip3, growth_keys=GROWTH_KEYS, code=code)

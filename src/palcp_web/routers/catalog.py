"""Browse the curated common-items catalog and add a fully-coded, auto-priced
care item to a case in one click. Pricing is applied at compute time (when the
case page renders), so the added line shows its VA price immediately."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from palcp.catalog import load_catalog, search

from ..db import get_db
from ..models import CareItemRow, User
from ..security import current_user, record_audit
from ..templating import flash, render
from .cases import get_owned_case

router = APIRouter()


@router.get("/cases/{case_id}/catalog")
def browse_catalog(case_id: int, request: Request, q: str = "",
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    return render(request, "catalog/list.html", user=user, case=case,
                  entries=search(q), q=q)


@router.post("/cases/{case_id}/catalog/add")
def add_from_catalog(case_id: int, request: Request, key: str = Form(...),
                     user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    entry = next((e for e in load_catalog() if e["key"] == key), None)
    if entry is None:
        flash(request, "Unknown catalog item.", "error")
        return RedirectResponse(f"/cases/{case.id}/catalog", status_code=303)
    sort_order = max((i.sort_order for i in case.items), default=0) + 1
    row = CareItemRow(
        case_id=case.id, sort_order=sort_order,
        category=entry.get("category", "Uncategorized"),
        item=entry["label"], code=entry.get("code", ""),
        code_type=entry.get("code_type", ""),
        growth_key=entry.get("growth_key", "medical_services"),
        frequency_per_year=entry.get("typical_frequency"),
        every_n_years=entry.get("every_n_years"),
        notes=entry.get("note", ""),
        geographic_basis=case.geo_zip3 or "")
    db.add(row)
    db.flush()
    record_audit(db, user_id=user.id, case_id=case.id, entity="item",
                 entity_id=row.id, action="create",
                 summary=f"Added '{row.item}' from catalog")
    db.commit()
    flash(request, f"Added '{row.item}' — priced from VA at this case's locality.",
          "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)

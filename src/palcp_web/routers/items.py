"""Care-item management: add (HTMX), edit, delete, and CSV/XLSX import."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..forms import as_bool, clean, opt_float
from ..models import CareItemRow, Case, User
from ..security import current_user, record_audit
from ..services import GROWTH_KEYS, compute_case
from ..templating import flash, render, render_partial
from .cases import get_owned_case

router = APIRouter()


def _items_section(request: Request, db: Session, case: Case):
    """Re-render the items table + live totals (HTMX swap target)."""
    db.refresh(case)
    comp = compute_case(case)
    return render_partial(request, "cases/_items_section.html", case=case,
                          result=comp.result, validation=comp.validation,
                          growth_keys=GROWTH_KEYS)


def _row_from_form(form: dict, case_id: int, sort_order: int) -> CareItemRow:
    return CareItemRow(
        case_id=case_id,
        sort_order=sort_order,
        category=clean(form.get("category")) or "Uncategorized",
        item=clean(form.get("item")),
        description=clean(form.get("description")),
        code=clean(form.get("code")),
        code_type=clean(form.get("code_type")),
        pricing_source=clean(form.get("pricing_source")),
        percentile=opt_float(form.get("percentile")),
        geographic_basis=clean(form.get("geographic_basis")),
        retrieval_date=clean(form.get("retrieval_date")),
        unit_cost=opt_float(form.get("unit_cost")) or 0.0,
        units_per_occurrence=opt_float(form.get("units_per_occurrence")) or 1.0,
        frequency_per_year=opt_float(form.get("frequency_per_year")),
        every_n_years=opt_float(form.get("every_n_years")),
        one_time=as_bool(form.get("one_time")),
        one_time_age=opt_float(form.get("one_time_age")),
        start_age=opt_float(form.get("start_age")),
        end_age=opt_float(form.get("end_age")),
        growth_key=clean(form.get("growth_key")) or "medical_services",
        medical_foundation=clean(form.get("medical_foundation")),
        notes=clean(form.get("notes")),
        va_setting=clean(form.get("va_setting")) or "non_facility",
    )


@router.post("/cases/{case_id}/items")
async def add_item(case_id: int, request: Request,
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    form = dict(await request.form())
    sort_order = (max((i.sort_order for i in case.items), default=0)) + 1
    row = _row_from_form(form, case.id, sort_order)
    if not row.item:
        raise HTTPException(status_code=400, detail="Item name is required")
    db.add(row)
    db.flush()
    record_audit(db, user_id=user.id, case_id=case.id, entity="item",
                 entity_id=row.id, action="create", summary=f"Added item '{row.item}'")
    db.commit()
    return _items_section(request, db, case)


@router.post("/cases/{case_id}/items/{item_id}/delete")
def delete_item(case_id: int, item_id: int, request: Request,
                user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    row = db.get(CareItemRow, item_id)
    if row is None or row.case_id != case.id:
        raise HTTPException(status_code=404)
    name = row.item
    db.delete(row)
    record_audit(db, user_id=user.id, case_id=case.id, entity="item",
                 entity_id=item_id, action="delete", summary=f"Deleted item '{name}'")
    db.commit()
    return _items_section(request, db, case)


@router.get("/cases/{case_id}/items/{item_id}/edit")
def edit_item_form(case_id: int, item_id: int, request: Request,
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    row = db.get(CareItemRow, item_id)
    if row is None or row.case_id != case.id:
        raise HTTPException(status_code=404)
    return render(request, "cases/item_form.html", user=user, case=case, item=row,
                  growth_keys=GROWTH_KEYS)


@router.post("/cases/{case_id}/items/{item_id}")
async def update_item(case_id: int, item_id: int, request: Request,
                      user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    row = db.get(CareItemRow, item_id)
    if row is None or row.case_id != case.id:
        raise HTTPException(status_code=404)
    form = dict(await request.form())
    updated = _row_from_form(form, case.id, row.sort_order)
    for field in (
        "category", "item", "description", "code", "code_type", "pricing_source",
        "percentile", "geographic_basis", "retrieval_date", "unit_cost",
        "units_per_occurrence", "frequency_per_year", "every_n_years", "one_time",
        "one_time_age", "start_age", "end_age", "growth_key", "medical_foundation",
        "notes", "va_setting",
    ):
        setattr(row, field, getattr(updated, field))
    record_audit(db, user_id=user.id, case_id=case.id, entity="item",
                 entity_id=row.id, action="update", summary=f"Edited item '{row.item}'")
    db.commit()
    flash(request, "Item saved.", "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.post("/cases/{case_id}/import-items")
async def import_items(case_id: int, request: Request,
                       user: User = Depends(current_user),
                       file: UploadFile = File(...),
                       db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    from palcp import load_items

    suffix = Path(file.filename or "items.csv").suffix or ".csv"
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            items = load_items(tmp.name)
        except Exception as exc:  # surface parse errors to the user
            flash(request, f"Could not import: {exc}", "error")
            return RedirectResponse(f"/cases/{case.id}", status_code=303)

    sort_order = (max((i.sort_order for i in case.items), default=0))
    for it in items:
        sort_order += 1
        db.add(CareItemRow(
            case_id=case.id, sort_order=sort_order, category=it.category,
            item=it.item, description=it.description, code=it.code,
            code_type=it.code_type, pricing_source=it.pricing_source,
            percentile=it.percentile, geographic_basis=it.geographic_basis,
            retrieval_date=it.retrieval_date, unit_cost=it.unit_cost,
            units_per_occurrence=it.units_per_occurrence,
            frequency_per_year=it.frequency_per_year, every_n_years=it.every_n_years,
            one_time=it.one_time, one_time_age=it.one_time_age,
            start_age=it.start_age, end_age=it.end_age, growth_key=it.growth_key,
            medical_foundation=it.medical_foundation, notes=it.notes,
        ))
    record_audit(db, user_id=user.id, case_id=case.id, entity="item",
                 action="create", summary=f"Imported {len(items)} item(s)")
    db.commit()
    flash(request, f"Imported {len(items)} care item(s).", "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)

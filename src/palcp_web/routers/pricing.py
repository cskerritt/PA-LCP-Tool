"""Pricing-table libraries: create, upload records, view, delete."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..forms import clean
from ..models import PriceRecordRow, PricingTable, User
from ..security import current_user
from ..templating import flash, render

router = APIRouter()

PRESETS = ["", "va_reasonable_charges", "cms_dmepos", "mfus"]


def _owned_table(db: Session, user: User, table_id: int) -> PricingTable:
    pt = db.get(PricingTable, table_id)
    if pt is None or pt.user_id != user.id:
        raise HTTPException(status_code=404)
    return pt


def _ingest(db: Session, table: PricingTable, data: bytes, filename: str,
            preset: str) -> int:
    from palcp import load_pricing

    suffix = Path(filename or "pricing.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        loaded = load_pricing(tmp.name, preset=(preset or None))
    for r in loaded.records:
        db.add(PriceRecordRow(
            table_id=table.id, source=r.source or table.name, code=r.code,
            code_type=r.code_type, description=r.description, amount=r.amount,
            percentile=r.percentile, geographic_area=r.geographic_area,
            effective_date=r.effective_date, citation_url=r.citation_url,
        ))
    return len(loaded.records)


@router.get("/pricing")
def list_pricing(request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    tables = db.scalars(
        select(PricingTable).where(PricingTable.user_id == user.id)
        .order_by(PricingTable.updated_at.desc())).all()
    return render(request, "pricing/list.html", user=user, tables=tables,
                  presets=PRESETS)


@router.get("/pricing/new")
def new_pricing(request: Request, user: User = Depends(current_user)):
    return render(request, "pricing/form.html", user=user, presets=PRESETS)


@router.post("/pricing")
async def create_pricing(request: Request, user: User = Depends(current_user),
                         name: str = Form(...), description: str = Form(""),
                         preset: str = Form(""),
                         file: UploadFile | None = File(None),
                         db: Session = Depends(get_db)):
    table = PricingTable(user_id=user.id, name=clean(name) or "Pricing table",
                         description=clean(description))
    db.add(table)
    db.flush()
    n = 0
    if file is not None and file.filename:
        data = await file.read()
        try:
            n = _ingest(db, table, data, file.filename, preset)
        except Exception as exc:
            db.rollback()
            flash(request, f"Could not load pricing file: {exc}", "error")
            return RedirectResponse("/pricing/new", status_code=303)
    db.commit()
    flash(request, f"Created pricing table '{table.name}' ({n} record(s)).",
          "success")
    return RedirectResponse(f"/pricing/{table.id}", status_code=303)


@router.get("/pricing/{table_id}")
def pricing_detail(table_id: int, request: Request,
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    table = _owned_table(db, user, table_id)
    return render(request, "pricing/detail.html", user=user, table=table,
                  presets=PRESETS, records=table.records[:500],
                  record_count=len(table.records))


@router.post("/pricing/{table_id}/upload")
async def upload_records(table_id: int, request: Request,
                         user: User = Depends(current_user),
                         preset: str = Form(""),
                         file: UploadFile = File(...),
                         db: Session = Depends(get_db)):
    table = _owned_table(db, user, table_id)
    data = await file.read()
    try:
        n = _ingest(db, table, data, file.filename or "", preset)
    except Exception as exc:
        db.rollback()
        flash(request, f"Could not load file: {exc}", "error")
        return RedirectResponse(f"/pricing/{table.id}", status_code=303)
    db.commit()
    flash(request, f"Added {n} record(s).", "success")
    return RedirectResponse(f"/pricing/{table.id}", status_code=303)


@router.post("/pricing/{table_id}/delete")
def delete_pricing(table_id: int, request: Request,
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    table = _owned_table(db, user, table_id)
    name = table.name
    db.delete(table)
    db.commit()
    flash(request, f"Deleted pricing table '{name}'.", "info")
    return RedirectResponse("/pricing", status_code=303)

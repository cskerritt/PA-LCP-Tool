"""Reusable growth-rate (assumption) libraries."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..forms import clean, opt_float
from ..models import RateLibrary, RateLibraryEntry, User
from ..security import current_user
from ..templating import flash, render
from palcp.config import DEFAULT_GROWTH_KEYS, default_growth_rates

router = APIRouter()


def _owned_library(db: Session, user: User, library_id: int) -> RateLibrary:
    lib = db.get(RateLibrary, library_id)
    if lib is None or lib.user_id != user.id:
        raise HTTPException(status_code=404)
    return lib


@router.get("/rates")
def list_rates(request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    libs = db.scalars(
        select(RateLibrary).where(RateLibrary.user_id == user.id)
        .order_by(RateLibrary.updated_at.desc())).all()
    return render(request, "rates/list.html", user=user, libraries=libs)


@router.post("/rates")
def create_rates(request: Request, user: User = Depends(current_user),
                 name: str = Form(...), description: str = Form(""),
                 db: Session = Depends(get_db)):
    lib = RateLibrary(user_id=user.id, name=clean(name) or "Rate library",
                      description=clean(description))
    # Seed with the standard growth keys (placeholder rates, editable).
    for key, gr in default_growth_rates().items():
        lib.entries.append(RateLibraryEntry(
            key=key, label=gr.label, annual_rate=gr.annual_rate,
            source=gr.source, citation_url=gr.citation_url, as_of=gr.as_of,
            note=gr.note))
    db.add(lib)
    db.commit()
    flash(request, f"Created rate library '{lib.name}'.", "success")
    return RedirectResponse(f"/rates/{lib.id}", status_code=303)


@router.get("/rates/{library_id}")
def rate_detail(library_id: int, request: Request,
                user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    lib = _owned_library(db, user, library_id)
    return render(request, "rates/form.html", user=user, library=lib)


@router.post("/rates/{library_id}")
async def update_rates(library_id: int, request: Request,
                       user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    lib = _owned_library(db, user, library_id)
    form = dict(await request.form())
    lib.name = clean(form.get("name")) or lib.name
    lib.description = clean(form.get("description"))
    for entry in lib.entries:
        rate = opt_float(form.get(f"e_{entry.key}_rate"))
        if rate is not None:
            entry.annual_rate = rate
        if f"e_{entry.key}_label" in form:
            entry.label = clean(form.get(f"e_{entry.key}_label"))
        if f"e_{entry.key}_source" in form:
            entry.source = clean(form.get(f"e_{entry.key}_source"))
        if f"e_{entry.key}_as_of" in form:
            entry.as_of = clean(form.get(f"e_{entry.key}_as_of"))
    db.commit()
    flash(request, "Rate library saved.", "success")
    return RedirectResponse(f"/rates/{lib.id}", status_code=303)


@router.post("/rates/{library_id}/delete")
def delete_rates(library_id: int, request: Request,
                 user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    lib = _owned_library(db, user, library_id)
    name = lib.name
    db.delete(lib)
    db.commit()
    flash(request, f"Deleted rate library '{name}'.", "info")
    return RedirectResponse("/rates", status_code=303)

"""Dashboard and case management (assumptions, growth rates, validation, history)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..forms import as_bool, clean, opt_float, opt_int
from ..models import (
    AuditLog,
    Case,
    CaseGrowthRate,
    CasePricingLink,
    PricingTable,
    RateLibrary,
    User,
)
from ..security import current_user, record_audit
from ..services import GROWTH_KEYS, compute_case, seed_growth_rate_rows
from ..templating import flash, render, render_partial

router = APIRouter()


def get_owned_case(db: Session, user: User, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if case is None or case.user_id != user.id:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _apply_assumptions(case: Case, form: dict) -> None:
    case.name = clean(form.get("name")) or case.name
    case.jurisdiction = clean(form.get("jurisdiction"))
    case.evaluator = clean(form.get("evaluator"))
    case.evaluator_credentials = clean(form.get("evaluator_credentials"))
    case.report_date = clean(form.get("report_date"))
    case.base_year = opt_int(form.get("base_year"))
    case.percentile_policy = opt_float(form.get("percentile_policy")) or 80.0
    case.collateral_source_note = clean(form.get("collateral_source_note"))
    # Claimant
    case.claimant_name = clean(form.get("claimant_name"))
    case.claimant_dob = clean(form.get("claimant_dob"))
    case.claimant_sex = clean(form.get("claimant_sex")) or "total"
    case.age_at_report = opt_float(form.get("age_at_report"))
    case.residence = clean(form.get("residence"))
    # Life expectancy
    case.le_additional_years = opt_float(form.get("le_additional_years")) or 0.0
    case.le_source = clean(form.get("le_source"))
    case.le_citation_url = clean(form.get("le_citation_url"))
    case.le_as_of = clean(form.get("le_as_of"))
    case.le_note = clean(form.get("le_note"))
    # Discount
    case.discount_rate = opt_float(form.get("discount_rate")) or 0.0
    case.discount_basis = clean(form.get("discount_basis")) or "nominal"
    case.discount_timing = clean(form.get("discount_timing")) or "mid_year"
    case.discount_source = clean(form.get("discount_source"))
    case.discount_citation_url = clean(form.get("discount_citation_url"))
    case.discount_as_of = clean(form.get("discount_as_of"))


@router.get("/")
def dashboard(request: Request, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    cases = db.scalars(
        select(Case).where(Case.user_id == user.id).order_by(Case.updated_at.desc())
    ).all()
    rows = []
    for c in cases:
        latest = c.reports[0] if c.reports else None
        rows.append({"case": c, "item_count": len(c.items), "latest": latest})
    return render(request, "dashboard.html", user=user, rows=rows)


@router.get("/cases/new")
def new_case(request: Request, user: User = Depends(current_user)):
    return render(request, "cases/form.html", user=user, case=None)


@router.post("/cases")
def create_case(request: Request, user: User = Depends(current_user),
                name: str = Form(...), db: Session = Depends(get_db)):
    case = Case(user_id=user.id, name=clean(name) or "Untitled case",
                evaluator=user.full_name, evaluator_credentials=user.credentials)
    case.growth_rates = seed_growth_rate_rows(case)
    db.add(case)
    db.flush()
    record_audit(db, user_id=user.id, case_id=case.id, entity="case",
                 entity_id=case.id, action="create", summary=f"Created case '{case.name}'")
    db.commit()
    flash(request, "Case created. Fill in the assumptions and add care items.",
          "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.get("/cases/{case_id}")
def case_detail(case_id: int, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    comp = compute_case(case)
    all_pricing = db.scalars(
        select(PricingTable).where(PricingTable.user_id == user.id)).all()
    linked_ids = {link.pricing_table_id for link in case.pricing_links}
    rate_libs = db.scalars(
        select(RateLibrary).where(RateLibrary.user_id == user.id)).all()
    return render(request, "cases/detail.html", user=user, case=case,
                  result=comp.result, validation=comp.validation,
                  all_pricing=all_pricing, linked_ids=linked_ids,
                  rate_libs=rate_libs, growth_keys=GROWTH_KEYS)


@router.get("/cases/{case_id}/edit")
def edit_case(case_id: int, request: Request, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    return render(request, "cases/form.html", user=user, case=case)


@router.post("/cases/{case_id}")
async def update_case(case_id: int, request: Request,
                      user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    form = dict(await request.form())
    _apply_assumptions(case, form)
    # Growth rates: inputs named gr_<key>_rate / _source / _as_of.
    for gr in case.growth_rates:
        rate = opt_float(form.get(f"gr_{gr.key}_rate"))
        if rate is not None:
            gr.annual_rate = rate
        if f"gr_{gr.key}_source" in form:
            gr.source = clean(form.get(f"gr_{gr.key}_source"))
        if f"gr_{gr.key}_as_of" in form:
            gr.as_of = clean(form.get(f"gr_{gr.key}_as_of"))
    record_audit(db, user_id=user.id, case_id=case.id, entity="case",
                 entity_id=case.id, action="update", summary="Updated assumptions")
    db.commit()
    flash(request, "Assumptions saved.", "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.post("/cases/{case_id}/delete")
def delete_case(case_id: int, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    name = case.name
    db.delete(case)
    record_audit(db, user_id=user.id, entity="case", action="delete",
                 summary=f"Deleted case '{name}'")
    db.commit()
    flash(request, f"Deleted case '{name}'.", "info")
    return RedirectResponse("/", status_code=303)


@router.get("/cases/{case_id}/validate")
def validate_fragment(case_id: int, request: Request,
                      user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    comp = compute_case(case)
    return render_partial(request, "cases/_validation.html",
                          validation=comp.validation, result=comp.result, case=case)


@router.post("/cases/{case_id}/pricing/link")
def link_pricing(case_id: int, request: Request,
                 user: User = Depends(current_user),
                 pricing_table_id: int = Form(...),
                 db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    pt = db.get(PricingTable, pricing_table_id)
    if pt is None or pt.user_id != user.id:
        raise HTTPException(status_code=404)
    exists = db.scalar(select(CasePricingLink).where(
        CasePricingLink.case_id == case.id,
        CasePricingLink.pricing_table_id == pt.id))
    if not exists:
        db.add(CasePricingLink(case_id=case.id, pricing_table_id=pt.id))
        db.commit()
        flash(request, f"Linked pricing table '{pt.name}'.", "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.post("/cases/{case_id}/pricing/{table_id}/unlink")
def unlink_pricing(case_id: int, table_id: int, request: Request,
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    link = db.scalar(select(CasePricingLink).where(
        CasePricingLink.case_id == case.id,
        CasePricingLink.pricing_table_id == table_id))
    if link:
        db.delete(link)
        db.commit()
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.post("/cases/{case_id}/rates/apply")
def apply_rate_library(case_id: int, request: Request,
                       user: User = Depends(current_user),
                       rate_library_id: int = Form(...),
                       db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    lib = db.get(RateLibrary, rate_library_id)
    if lib is None or lib.user_id != user.id:
        raise HTTPException(status_code=404)
    existing = {gr.key: gr for gr in case.growth_rates}
    for entry in lib.entries:
        gr = existing.get(entry.key)
        if gr is None:
            gr = CaseGrowthRate(case_id=case.id, key=entry.key)
            db.add(gr)
            existing[entry.key] = gr
        gr.label = entry.label
        gr.annual_rate = entry.annual_rate
        gr.source = entry.source
        gr.citation_url = entry.citation_url
        gr.as_of = entry.as_of
        gr.note = entry.note
    record_audit(db, user_id=user.id, case_id=case.id, entity="case",
                 entity_id=case.id, action="update",
                 summary=f"Applied rate library '{lib.name}'")
    db.commit()
    flash(request, f"Applied rate library '{lib.name}'.", "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.get("/cases/{case_id}/history")
def case_history(case_id: int, request: Request,
                 user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    entries = db.scalars(
        select(AuditLog).where(AuditLog.case_id == case.id)
        .order_by(AuditLog.created_at.desc()).limit(200)).all()
    return render(request, "cases/history.html", user=user, case=case,
                  entries=entries)

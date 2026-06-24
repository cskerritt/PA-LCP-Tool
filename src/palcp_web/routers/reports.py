"""Generate, download, and delete Excel reports for a case."""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Report, User
from ..security import current_user, record_audit
from ..services import build_case_workbook_bytes
from ..templating import flash
from .cases import get_owned_case

router = APIRouter()

XLSX_MEDIA = ("application/vnd.openxmlformats-officedocument."
              "spreadsheetml.sheet")


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "life_care_plan")).strip("_")
    return s or "life_care_plan"


@router.post("/cases/{case_id}/report")
def generate_report(case_id: int, request: Request,
                    user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    generated_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    data, comp = build_case_workbook_bytes(case, generated_on)
    filename = f"{_slug(case.name)}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    report = Report(
        case_id=case.id, user_id=user.id, generated_on=generated_on,
        filename=filename,
        total_current=comp.result.grand_total_current,
        total_nominal=comp.result.grand_total_nominal,
        total_present_value=comp.result.grand_total_present_value,
        validation_summary=comp.validation.summary(),
        workbook=data,
    )
    db.add(report)
    record_audit(db, user_id=user.id, case_id=case.id, entity="report",
                 action="create",
                 summary=f"Generated report (PV ${comp.result.grand_total_present_value:,.0f})")
    db.commit()
    if comp.validation.errors:
        flash(request, f"Report generated with {len(comp.validation.errors)} "
                       f"validation error(s) — review the Validation tab.", "error")
    else:
        flash(request, "Report generated.", "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None or report.user_id != user.id:
        raise HTTPException(status_code=404)
    headers = {"Content-Disposition": f'attachment; filename="{report.filename}"'}
    return Response(content=report.workbook, media_type=XLSX_MEDIA, headers=headers)


@router.post("/reports/{report_id}/delete")
def delete_report(report_id: int, request: Request,
                  user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None or report.user_id != user.id:
        raise HTTPException(status_code=404)
    case_id = report.case_id
    db.delete(report)
    db.commit()
    flash(request, "Report deleted.", "info")
    return RedirectResponse(f"/cases/{case_id}", status_code=303)

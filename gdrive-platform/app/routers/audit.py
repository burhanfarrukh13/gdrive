"""Audit log viewer."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..tpl import templates
from ..db import AuditLog, get_db
from ..deps import require_perm
from ..permissions import can


router = APIRouter()


@router.get("/audit", response_class=HTMLResponse)
def audit_log(request: Request, db: Session = Depends(get_db), user=Depends(require_perm("audit.view"))):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(300).all()
    return templates.TemplateResponse("audit/list.html", {
        "request": request, "user": user, "rows": rows, "can": can,
    })

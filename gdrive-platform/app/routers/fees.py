"""Fees view + payment recording.

A fee is a price attached to an AccessGrant. The seller (or whoever grants
access) records the agreed price; the manager/owner later marks it paid
and notes where the money landed. Sellers can VIEW the fees ledger so they
know what's outstanding for the students they onboarded, but only
manager+ can mark a fee paid (requires `fees.update`).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..tpl import templates
from ..db import (
    AccessGrant, AccessStatus, FeeStatus, Student, get_db,
)
from ..deps import require_perm, flash, apply_flash_to_response
from ..audit import log
from ..permissions import can
from ..distribution import sync_revenue_for_grant


router = APIRouter()


def _seller_filter(query, user):
    """Restrict a query to grants the seller themselves created.

    Managers/owner/admin/accountant see everything.
    """
    if user.role.value == "seller":
        return query.filter(AccessGrant.granted_by_id == user.id)
    return query


@router.get("/fees", response_class=HTMLResponse)
def fees_list(
    request: Request,
    status_filter: str = "all",
    student_id: str = "",
    missing_price: str = "0",
    db: Session = Depends(get_db),
    user=Depends(require_perm("fees.view")),
):
    student_id_int: int | None = int(student_id) if student_id.strip().isdigit() else None

    # Show ALL active/revoked/expired grants, not just ones with a price,
    # so the seller/manager can SEE which sales are missing a price and
    # backfill them. The 'missing price' filter is a quick way to surface them.
    q = db.query(AccessGrant).join(Student).join(AccessGrant.folder).filter(
        AccessGrant.status != AccessStatus.expired
    )
    q = _seller_filter(q, user)

    if missing_price == "1":
        q = q.filter(
            (AccessGrant.price_amount.is_(None)) | (AccessGrant.price_amount == 0)
        )
    elif status_filter != "all":
        try:
            q = q.filter(AccessGrant.fee_status == FeeStatus(status_filter))
        except ValueError:
            status_filter = "all"
    if student_id_int:
        q = q.filter(AccessGrant.student_id == student_id_int)

    grants = q.order_by(AccessGrant.granted_at.desc()).all()

    # Totals for the same scope.
    totals_q = db.query(
        AccessGrant.fee_status,
        func.coalesce(func.sum(AccessGrant.price_amount), 0.0),
    ).filter(
        AccessGrant.status != AccessStatus.expired,
        AccessGrant.price_amount.isnot(None),
        AccessGrant.price_amount > 0,
    )
    totals_q = _seller_filter(totals_q, user)
    totals = {"pending": 0.0, "paid": 0.0, "waived": 0.0, "all": 0.0}
    for st, amt in totals_q.all():
        key = st.value if hasattr(st, "value") else str(st)
        totals[key] = round(float(amt), 2)
        totals["all"] += float(amt)
    totals["all"] = round(totals["all"], 2)

    # Count of grants missing a price (in this scope).
    missing_q = db.query(func.count(AccessGrant.id)).filter(
        AccessGrant.status != AccessStatus.expired,
        (AccessGrant.price_amount.is_(None)) | (AccessGrant.price_amount == 0),
    )
    missing_q = _seller_filter(missing_q, user)
    missing_price_count = missing_q.scalar() or 0

    students_q = db.query(Student).filter(Student.is_active == True).order_by(Student.full_name)  # noqa: E712
    if user.role.value == "seller":
        seller_student_ids = db.query(AccessGrant.student_id).filter(
            AccessGrant.granted_by_id == user.id
        ).distinct().all()
        students_q = students_q.filter(Student.id.in_([row[0] for row in seller_student_ids]))
    students = students_q.all()

    return templates.TemplateResponse("fees/list.html", {
        "request": request, "user": user, "grants": grants, "students": students,
        "status_filter": status_filter, "student_id": student_id_int,
        "missing_price": missing_price, "missing_price_count": missing_price_count,
        "totals": totals, "can": can,
        "FeeStatus": FeeStatus, "is_seller_scope": user.role.value == "seller",
    })


@router.post("/fees/{gid}/mark-paid")
def mark_fee_paid(
    gid: int,
    request: Request,
    paid_on: str = Form(""),
    credit_account: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("fees.update")),
):
    g = db.query(AccessGrant).filter(AccessGrant.id == gid).first()
    if not g:
        raise HTTPException(404)
    try:
        g.fee_paid_on = date.fromisoformat(paid_on) if paid_on else date.today()
    except ValueError:
        flash(request, "Invalid paid-on date (use YYYY-MM-DD).", level="error")
        return apply_flash_to_response(
            request,
            RedirectResponse(request.headers.get("referer", "/fees"), status_code=303),
        )
    g.fee_status = FeeStatus.paid
    if credit_account.strip():
        g.fee_credit_account = credit_account.strip()[:160]
    sync_revenue_for_grant(db, g)
    log(db, action="fee.paid", actor_user_id=user.id, target_type="grant", target_id=g.id,
        detail=f"{g.student.full_name} → {g.folder.label}: {g.price_amount} {g.price_currency} "
               f"→ {g.fee_credit_account or '—'}")
    db.commit()
    flash(request, f"Fee marked paid for {g.student.full_name} → \"{g.folder.label}\". Revenue updated.", level="success")
    return apply_flash_to_response(
        request,
        RedirectResponse(request.headers.get("referer", "/fees"), status_code=303),
    )


@router.post("/fees/{gid}/waive")
def waive_fee(
    gid: int,
    request: Request,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("fees.update")),
):
    g = db.query(AccessGrant).filter(AccessGrant.id == gid).first()
    if not g:
        raise HTTPException(404)
    g.fee_status = FeeStatus.waived
    if reason.strip():
        g.notes = (g.notes + "\n" if g.notes else "") + f"Waived: {reason.strip()}"
    sync_revenue_for_grant(db, g)
    log(db, action="fee.waive", actor_user_id=user.id, target_type="grant", target_id=g.id,
        detail=f"{g.student.full_name} → {g.folder.label}: waived ({reason.strip() or 'no reason'})")
    db.commit()
    flash(request, f"Fee waived for {g.student.full_name} → \"{g.folder.label}\".", level="success")
    return apply_flash_to_response(
        request,
        RedirectResponse(request.headers.get("referer", "/fees"), status_code=303),
    )


@router.post("/fees/{gid}/edit")
def edit_fee(
    gid: int,
    request: Request,
    price_amount: str = Form(...),
    price_currency: str = Form("PKR"),
    fee_credit_account: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("fees.update")),
):
    """Correct a price or credit-account label after the fact."""
    g = db.query(AccessGrant).filter(AccessGrant.id == gid).first()
    if not g:
        raise HTTPException(404)
    try:
        new_price = float(price_amount) if price_amount not in (None, "") else 0.0
        if new_price < 0:
            raise ValueError
    except ValueError:
        flash(request, "Price must be a non-negative number.", level="error")
        return apply_flash_to_response(
            request,
            RedirectResponse(request.headers.get("referer", "/fees"), status_code=303),
        )
    g.price_amount = new_price
    g.price_currency = (price_currency or "PKR").strip().upper()[:8] or "PKR"
    g.fee_credit_account = fee_credit_account.strip()[:160] or None
    # If we previously had no fee, set to pending; if we cleared the price, leave status as-is.
    if g.price_amount and g.price_amount > 0 and g.fee_status is None:
        g.fee_status = FeeStatus.pending
    sync_revenue_for_grant(db, g)
    log(db, action="fee.edit", actor_user_id=user.id, target_type="grant", target_id=g.id,
        detail=f"{g.student.full_name} → {g.folder.label}: price={g.price_amount} {g.price_currency}, "
               f"credited_to={g.fee_credit_account or '—'}")
    db.commit()
    flash(request, f"Fee updated for {g.student.full_name} → \"{g.folder.label}\". Revenue synced.", level="success")
    return apply_flash_to_response(
        request,
        RedirectResponse(request.headers.get("referer", "/fees"), status_code=303),
    )

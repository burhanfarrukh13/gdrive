"""Revenue (unified with fees), Receivables, Payouts.

UNIFICATION NOTE (v1.3):
  Fees and revenue are the same thing. A fee on an AccessGrant that gets
  marked paid auto-creates a RevenueEvent with status=received, which
  drives the revenue tiles, the /revenue list, and the payouts engine.
  See app/distribution.py:sync_revenue_for_grant().

  The /revenue page is now a *read-only* view of all RevenueEvents,
  including those synced from fees (source='fee') plus any general-income
  events (source != 'fee') that accountants record manually.

  The standalone POST /revenue/new has been removed. New revenue always
  starts as a fee on a grant — record it on the student's "Sell access"
  modal. This avoids the duplicate-ledger problem the old design had.
"""
from datetime import datetime, date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..tpl import templates
from ..db import (
    Student, User, RevenueEvent, RevenueStatus,
    Payout, PayoutStatus, get_db,
)
from ..deps import require_perm, flash, apply_flash_to_response
from ..audit import log
from ..distribution import (
    compute_distributions_for, build_payouts, mark_payout_paid, user_balance,
    sync_revenue_for_grant, backfill_fee_revenues,
)
from ..permissions import can


router = APIRouter()


# -------- Revenue --------

@router.get("/revenue", response_class=HTMLResponse)
def revenue_list(
    request: Request,
    status_filter: str = "all",
    student_id: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_perm("revenue.view")),
):
    # Backfill on every read so freshly-priced grants show up immediately.
    # Cheap on small DBs; on a large DB you'd move this to a scheduled job.
    backfill_fee_revenues(db)

    student_id_int: int | None = int(student_id) if student_id.strip().isdigit() else None
    q = db.query(RevenueEvent)
    if status_filter != "all":
        q = q.filter(RevenueEvent.status == RevenueStatus(status_filter))
    if student_id_int:
        q = q.filter(RevenueEvent.student_id == student_id_int)
    events = q.order_by(RevenueEvent.created_at.desc()).all()
    students = db.query(Student).filter(Student.is_active == True).order_by(Student.full_name).all()  # noqa: E712

    total_received = db.query(func.coalesce(func.sum(RevenueEvent.amount), 0.0)).filter(
        RevenueEvent.status == RevenueStatus.received,
    ).scalar() or 0.0
    total_pending = db.query(func.coalesce(func.sum(RevenueEvent.amount), 0.0)).filter(
        RevenueEvent.status == RevenueStatus.pending,
    ).scalar() or 0.0

    return templates.TemplateResponse("finance/revenue_list.html", {
        "request": request, "user": user, "events": events, "students": students,
        "status_filter": status_filter, "student_id": student_id_int,
        "total_received": round(float(total_received), 2),
        "total_pending": round(float(total_pending), 2),
        "can": can, "RevenueStatus": RevenueStatus,
    })


@router.post("/revenue/new")
def create_revenue_disabled():
    """Legacy endpoint kept for compatibility.

    New revenue always starts as a fee on a grant — see the "Sell access"
    modal on a student page. Redirect there.
    """
    return RedirectResponse("/students", status_code=303)


@router.post("/revenue/{rid}/receive")
def mark_received(rid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("revenue.update"))):
    r = db.query(RevenueEvent).filter(RevenueEvent.id == rid).first()
    if not r:
        raise HTTPException(404)
    if r.status == RevenueStatus.received:
        return RedirectResponse("/revenue", status_code=303)
    r.status = RevenueStatus.received
    r.received_on = r.received_on or date.today()
    compute_distributions_for(db, r)
    # If this event is synced from a grant, mirror the status back to the grant.
    if r.source == "fee" and r.notes and r.notes.startswith("grant:"):
        try:
            gid = int(r.notes.split("|", 1)[0].split(":", 1)[1])
            from ..db import AccessGrant, FeeStatus
            g = db.query(AccessGrant).filter(AccessGrant.id == gid).first()
            if g:
                g.fee_status = FeeStatus.paid
                g.fee_paid_on = r.received_on
        except (ValueError, IndexError):
            pass
    log(db, action="revenue.received", actor_user_id=user.id, target_type="revenue", target_id=r.id)
    db.commit()
    return RedirectResponse("/revenue", status_code=303)


@router.post("/revenue/{rid}/cancel")
def cancel_revenue(rid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("revenue.delete"))):
    r = db.query(RevenueEvent).filter(RevenueEvent.id == rid).first()
    if not r:
        raise HTTPException(404)
    r.status = RevenueStatus.cancelled
    # Mirror cancel back to the source grant if there is one.
    if r.source == "fee" and r.notes and r.notes.startswith("grant:"):
        try:
            gid = int(r.notes.split("|", 1)[0].split(":", 1)[1])
            from ..db import AccessGrant, FeeStatus
            g = db.query(AccessGrant).filter(AccessGrant.id == gid).first()
            if g and g.fee_status == FeeStatus.paid:
                g.fee_status = FeeStatus.pending
                g.fee_paid_on = None
        except (ValueError, IndexError):
            pass
    log(db, action="revenue.cancel", actor_user_id=user.id, target_type="revenue", target_id=r.id)
    db.commit()
    return RedirectResponse("/revenue", status_code=303)


# -------- Payouts --------

@router.get("/payouts", response_class=HTMLResponse)
def payouts_list(
    request: Request,
    status_filter: str = "all",
    db: Session = Depends(get_db),
    user=Depends(require_perm("payouts.view")),
):
    q = db.query(Payout).join(User, Payout.user_id == User.id)
    if status_filter != "all":
        q = q.filter(Payout.status == PayoutStatus(status_filter))
    payouts = q.order_by(Payout.created_at.desc()).all()

    # Per-user outstanding balance
    balances = []
    members = db.query(User).filter(User.is_active == True, User.default_ratio > 0).all()  # noqa: E712
    for m in members:
        b = user_balance(db, m.id)
        if b > 0:
            balances.append((m, round(b, 2)))

    total_paid = db.query(func.coalesce(func.sum(Payout.amount), 0.0)).filter(
        Payout.status == PayoutStatus.paid,
    ).scalar() or 0.0
    total_pending = db.query(func.coalesce(func.sum(Payout.amount), 0.0)).filter(
        Payout.status == PayoutStatus.pending,
    ).scalar() or 0.0

    return templates.TemplateResponse("finance/payouts_list.html", {
        "request": request, "user": user, "payouts": payouts, "balances": balances,
        "status_filter": status_filter,
        "total_paid": round(float(total_paid), 2),
        "total_pending": round(float(total_pending), 2),
        "can": can, "PayoutStatus": PayoutStatus,
    })


@router.post("/payouts/build")
def payouts_build(
    request: Request,
    user_ids: list[int] = Form(...),
    period_label: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("payouts.create")),
):
    label = period_label.strip() or date.today().strftime("%Y-%m")
    payouts = build_payouts(db, user_ids, label)
    log(db, action="payouts.build", actor_user_id=user.id, target_type="payouts",
        detail=f"Built {len(payouts)} payouts for period {label}")
    db.commit()
    return RedirectResponse("/payouts", status_code=303)


@router.post("/payouts/{pid}/pay")
def pay_payout(
    pid: int,
    request: Request,
    method: str = Form(""),
    reference: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("payouts.update")),
):
    p = db.query(Payout).filter(Payout.id == pid).first()
    if not p:
        raise HTTPException(404)
    mark_payout_paid(db, p, method=method.strip() or None, reference=reference.strip() or None, paid_on=None)
    log(db, action="payout.paid", actor_user_id=user.id, target_type="payout", target_id=p.id,
        detail=f"{p.amount} → {p.user.full_name}")
    db.commit()
    return RedirectResponse("/payouts", status_code=303)

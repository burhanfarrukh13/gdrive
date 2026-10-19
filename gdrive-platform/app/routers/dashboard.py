"""Dashboard route — analytics overview."""
from datetime import datetime, timedelta, date
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..tpl import templates
from ..db import (
    User, Student, DriveFolder, AccessGrant, AccessStatus, FeeStatus,
    RevenueEvent, RevenueStatus, Payout, PayoutStatus, get_db,
)
from ..deps import require_user
from ..permissions import can


router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)

    now = datetime.utcnow()
    today = date.today()

    # Tiles
    total_students = db.query(Student).filter(Student.is_active == True).count()  # noqa: E712
    total_folders = db.query(DriveFolder).filter(DriveFolder.is_archived == False).count()  # noqa: E712
    active_grants = db.query(AccessGrant).filter(AccessGrant.status == AccessStatus.active).count()
    expiring_soon = db.query(AccessGrant).filter(
        AccessGrant.status == AccessStatus.active,
        AccessGrant.expires_at <= now + timedelta(days=7),
    ).count()

    total_received = db.query(func.coalesce(func.sum(RevenueEvent.amount), 0.0)).filter(
        RevenueEvent.status == RevenueStatus.received,
    ).scalar() or 0.0
    total_pending = db.query(func.coalesce(func.sum(RevenueEvent.amount), 0.0)).filter(
        RevenueEvent.status == RevenueStatus.pending,
    ).scalar() or 0.0
    total_paid_out = db.query(func.coalesce(func.sum(Payout.amount), 0.0)).filter(
        Payout.status == PayoutStatus.paid,
    ).scalar() or 0.0
    pending_payouts = db.query(func.coalesce(func.sum(Payout.amount), 0.0)).filter(
        Payout.status == PayoutStatus.pending,
    ).scalar() or 0.0

    # 14-day revenue trend
    rev_by_day = defaultdict(float)
    rows = db.query(RevenueEvent.received_on, RevenueEvent.amount).filter(
        RevenueEvent.status == RevenueStatus.received,
        RevenueEvent.received_on.isnot(None),
        RevenueEvent.received_on >= today - timedelta(days=13),
    ).all()
    for d, amt in rows:
        rev_by_day[d.isoformat()] += amt

    trend_labels = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    trend_values = [round(rev_by_day.get(d, 0.0), 2) for d in trend_labels]

    # Receivables by student (top 5)
    recv_rows = db.query(
        Student.full_name,
        func.coalesce(func.sum(RevenueEvent.amount), 0.0).label("amt"),
    ).join(RevenueEvent, RevenueEvent.student_id == Student.id).filter(
        RevenueEvent.status == RevenueStatus.pending,
    ).group_by(Student.id).order_by(func.sum(RevenueEvent.amount).desc()).limit(5).all()
    recv_labels = [r.full_name for r in recv_rows]
    recv_values = [round(float(r.amt), 2) for r in recv_rows]

    # Team member balance (pending payout)
    bal_rows = db.query(
        User.full_name,
        func.coalesce(func.sum(Payout.amount), 0.0).label("amt"),
    ).join(Payout, Payout.user_id == User.id).filter(
        Payout.status == PayoutStatus.pending,
    ).group_by(User.id).all()
    bal_labels = [r.full_name for r in bal_rows]
    bal_values = [round(float(r.amt), 2) for r in bal_rows]

    # Expiring grants (next 7 days)
    expiring_list = db.query(AccessGrant).join(Student).join(DriveFolder).filter(
        AccessGrant.status == AccessStatus.active,
        AccessGrant.expires_at <= now + timedelta(days=7),
    ).order_by(AccessGrant.expires_at.asc()).limit(8).all()

    # Fee totals (only show on the manager+ dashboard; for sellers we compute theirs-only)
    fees_q = db.query(
        AccessGrant.fee_status,
        func.coalesce(func.sum(AccessGrant.price_amount), 0.0),
    ).filter(
        AccessGrant.price_amount.isnot(None),
        AccessGrant.price_amount > 0,
    )
    if user.role.value == "seller":
        fees_q = fees_q.filter(AccessGrant.granted_by_id == user.id)
    fees_by_status = {"pending": 0.0, "paid": 0.0, "waived": 0.0}
    for st, amt in fees_q.all():
        key = st.value if hasattr(st, "value") else str(st)
        fees_by_status[key] = round(float(amt), 2)
    fees_outstanding = fees_by_status["pending"]
    fees_paid_total = fees_by_status["paid"]
    # Pending count for the badge on the sidebar/Fees page
    pending_fee_count = db.query(AccessGrant).filter(
        AccessGrant.fee_status == FeeStatus.pending,
        AccessGrant.price_amount.isnot(None),
        AccessGrant.price_amount > 0,
    )
    if user.role.value == "seller":
        pending_fee_count = pending_fee_count.filter(AccessGrant.granted_by_id == user.id)
    pending_fee_count = pending_fee_count.count()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "can": can,
        "tiles": {
            "students": total_students,
            "folders": total_folders,
            "active_grants": active_grants,
            "expiring_soon": expiring_soon,
            "received": round(float(total_received), 2),
            "pending": round(float(total_pending), 2),
            "paid_out": round(float(total_paid_out), 2),
            "pending_payouts": round(float(pending_payouts), 2),
            "fees_outstanding": round(fees_outstanding, 2),
            "fees_paid": round(fees_paid_total, 2),
            "fees_pending_count": pending_fee_count,
        },
        "trend_labels": trend_labels,
        "trend_values": trend_values,
        "recv_labels": recv_labels,
        "recv_values": recv_values,
        "bal_labels": bal_labels,
        "bal_values": bal_values,
        "expiring": expiring_list,
    })

"""Profit-distribution engine.

Given a RevenueEvent, compute per-user shares using either:
  - each active user's `default_ratio` (proportional)
  - or — if no ratios sum to 1 — a fixed equal split among active users
    that have a positive ratio.

We store the *applied* ratio per distribution so future ratio edits
don't change historical payouts.

UNIFICATION NOTE (v1.3):
  Fees and revenue are the same thing viewed two ways. When a fee on an
  AccessGrant is created, edited, marked paid, or waived, we call
  `sync_revenue_for_grant()` here to keep a matching RevenueEvent in sync.
  The /revenue page reads from these synced events (plus any general-income
  events that aren't tied to a grant), so dashboards stay consistent
  no matter which path the money arrived through.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from .db import (
    AccessGrant, FeeStatus, RevenueEvent, RevenueDistribution,
    RevenueStatus, User, UserRole, Payout, PayoutStatus,
)


def compute_distributions_for(db: Session, revenue: RevenueEvent) -> list[RevenueDistribution]:
    # Eligible users: active, with a positive ratio. Owners always included.
    users = db.query(User).filter(User.is_active == True, User.default_ratio > 0).all()  # noqa: E712

    if not users:
        return []

    total_ratio = sum(u.default_ratio for u in users)

    # If ratios don't add up to >= 0.999, fall back to equal split.
    use_proportional = total_ratio >= 0.999

    if use_proportional:
        # Normalize to total of 1.0 to absorb rounding drift.
        scale = 1.0 / total_ratio
        for u in users:
            amount = round(revenue.amount * u.default_ratio * scale, 2)
            db.add(RevenueDistribution(
                revenue_id=revenue.id,
                user_id=u.id,
                ratio=u.default_ratio * scale,
                amount=amount,
            ))
    else:
        share = round(revenue.amount / len(users), 2)
        for u in users:
            db.add(RevenueDistribution(
                revenue_id=revenue.id,
                user_id=u.id,
                ratio=1.0 / len(users),
                amount=share,
            ))
    db.flush()
    return db.query(RevenueDistribution).filter(RevenueDistribution.revenue_id == revenue.id).all()


def user_balance(db: Session, user_id: int) -> float:
    """Total unpaid distributions for a user."""
    from sqlalchemy import func
    total = db.query(func.coalesce(func.sum(RevenueDistribution.amount), 0.0)).filter(
        RevenueDistribution.user_id == user_id,
        RevenueDistribution.payout_id.is_(None),
    ).scalar()
    return float(total or 0.0)


def build_payouts(db: Session, user_ids: Iterable[int], period_label: str) -> list[Payout]:
    """Group all unpaid distributions for given users into one payout each."""
    payouts: list[Payout] = []
    for uid in user_ids:
        dists = db.query(RevenueDistribution).filter(
            RevenueDistribution.user_id == uid,
            RevenueDistribution.payout_id.is_(None),
        ).all()
        if not dists:
            continue
        total = round(sum(d.amount for d in dists), 2)
        payout = Payout(
            user_id=uid,
            amount=total,
            period_label=period_label,
            status=PayoutStatus.pending,
        )
        db.add(payout)
        db.flush()
        for d in dists:
            d.payout_id = payout.id
        payouts.append(payout)
    db.flush()
    return payouts


def mark_payout_paid(db: Session, payout: Payout, *, method: str | None, reference: str | None, paid_on: date | None) -> None:
    payout.status = PayoutStatus.paid
    payout.method = method
    payout.reference = reference
    payout.paid_on = paid_on or date.today()


# ---------------------------------------------------------------------------
# Fee <-> Revenue sync
# ---------------------------------------------------------------------------

# We tag events synced from a fee with this source so we can find them again.
FEE_REVENUE_SOURCE = "fee"


def _existing_fee_revenue(db: Session, grant_id: int) -> Optional[RevenueEvent]:
    return db.query(RevenueEvent).filter(
        RevenueEvent.source == FEE_REVENUE_SOURCE,
        RevenueEvent.notes.like(f"grant:{grant_id}|%"),
    ).first()


def sync_revenue_for_grant(db: Session, grant: AccessGrant) -> Optional[RevenueEvent]:
    """Keep a RevenueEvent in sync with the grant's fee.

    Behavior:
      * If the grant has no price (free comp / not priced yet) and no
        existing synced event, do nothing.
      * If the grant has a price and no existing synced event, create one
        with status pending/received/waived based on fee_status.
      * If the grant has an existing synced event, update it.
      * Waiving a fee cancels the corresponding event (status -> cancelled).

    Returns the synced event, or None if there's nothing to sync.
    """
    # Nothing to do if there's no price and no existing event.
    price = float(grant.price_amount or 0)
    existing = _existing_fee_revenue(db, grant.id)

    if price <= 0 and existing is None:
        return None
    if price <= 0 and existing is not None:
        # Price was cleared retroactively. Cancel the event so totals stay honest.
        existing.status = RevenueStatus.cancelled
        db.flush()
        return existing

    # We have a real price. Compute the target revenue status.
    if grant.fee_status == FeeStatus.paid:
        target_status = RevenueStatus.received
        target_received_on = grant.fee_paid_on or date.today()
    elif grant.fee_status == FeeStatus.pending:
        target_status = RevenueStatus.pending
        target_received_on = None
    elif grant.fee_status == FeeStatus.waived:
        target_status = RevenueStatus.cancelled
        target_received_on = None
    else:
        target_status = RevenueStatus.pending
        target_received_on = None

    notes = f"grant:{grant.id}|{grant.folder.label} for {grant.student.full_name}"

    if existing is None:
        event = RevenueEvent(
            student_id=grant.student_id,
            amount=price,
            currency=grant.price_currency or "PKR",
            source=FEE_REVENUE_SOURCE,
            status=target_status,
            received_on=target_received_on,
            notes=notes,
            recorded_by_id=grant.granted_by_id,
        )
        db.add(event)
        db.flush()
        if target_status == RevenueStatus.received:
            compute_distributions_for(db, event)
        return event

    # Update existing. If we just transitioned to received, compute distributions.
    was_received = existing.status == RevenueStatus.received
    existing.amount = price
    existing.currency = grant.price_currency or existing.currency or "PKR"
    existing.student_id = grant.student_id
    existing.status = target_status
    existing.received_on = target_received_on if target_status == RevenueStatus.received else None
    existing.notes = notes
    if target_status == RevenueStatus.received and not was_received:
        compute_distributions_for(db, existing)
    db.flush()
    return existing


def backfill_fee_revenues(db: Session) -> int:
    """One-time migration: for every priced grant, ensure a matching RevenueEvent.

    Returns the number of events created.
    """
    grants = db.query(AccessGrant).filter(
        AccessGrant.price_amount.isnot(None),
        AccessGrant.price_amount > 0,
    ).all()
    created = 0
    for g in grants:
        before = _existing_fee_revenue(db, g.id)
        sync_revenue_for_grant(db, g)
        after = _existing_fee_revenue(db, g.id)
        if before is None and after is not None:
            created += 1
    db.commit()
    return created
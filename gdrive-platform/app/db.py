"""SQLAlchemy database setup and ORM models."""
from __future__ import annotations

import enum
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    Float, ForeignKey, Enum, UniqueConstraint, Index,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import create_engine

from .config import get_settings


Base = declarative_base()


# ---------- Enums ----------

class UserRole(str, enum.Enum):
    owner = "owner"          # full access + can manage roles
    admin = "admin"          # full access, cannot edit role structure
    manager = "manager"      # students, folders, grants, view revenue
    accountant = "accountant"  # revenue, payouts, view-only on others
    seller = "seller"        # add students + grant access; mark fee paid; view-only on rest
    viewer = "viewer"        # read-only


class AccessStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class FeeStatus(str, enum.Enum):
    pending = "pending"     # price agreed, money not yet received
    paid = "paid"           # money received and recorded
    waived = "waived"       # seller/manager decided no charge (free comp, etc.)


class RevenueStatus(str, enum.Enum):
    pending = "pending"       # receivable, not yet received
    received = "received"     # money in
    cancelled = "cancelled"


class PayoutStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"


# ---------- Models ----------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(190), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.viewer)
    is_active = Column(Boolean, nullable=False, default=True)
    # Share ratio (0-1) of any revenue event this user receives by default.
    default_ratio = Column(Float, nullable=False, default=0.0)
    phone = Column(String(40), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payouts = relationship("Payout", back_populates="user", cascade="all,delete")


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(190), nullable=False, unique=True, index=True)
    phone = Column(String(40), nullable=True)
    # Google account that will receive the Drive permission.
    google_email = Column(String(190), nullable=False)
    course_or_batch = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    access_grants = relationship("AccessGrant", back_populates="student", cascade="all,delete")
    revenues = relationship("RevenueEvent", back_populates="student", cascade="all,delete")


class DriveFolder(Base):
    """A Drive folder we manage. We store the ID and a friendly label."""
    __tablename__ = "drive_folders"
    id = Column(Integer, primary_key=True)
    label = Column(String(160), nullable=False)
    drive_folder_id = Column(String(120), nullable=False, unique=True, index=True)
    drive_owner_email = Column(String(190), nullable=True)
    description = Column(Text, nullable=True)
    # The price we usually sell this folder for. Optional; if set, it
    # pre-fills the "Sell access" modal so you don't have to type it
    # every time. Per-grant prices still override this.
    default_price = Column(Float, nullable=True)
    default_currency = Column(String(8), nullable=True, default="PKR")
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AccessGrant(Base):
    """A student's permission on a specific Drive folder, with expiry."""
    __tablename__ = "access_grants"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey("drive_folders.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    status = Column(Enum(AccessStatus), nullable=False, default=AccessStatus.active)
    granted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    drive_permission_id = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)

    # --- Fee / pricing (added in seller role iteration) ---
    # The price the student is paying (or paid) for THIS grant.
    # Currency-agnostic number; default currency is PKR but can be set per grant.
    price_amount = Column(Float, nullable=True)
    price_currency = Column(String(8), nullable=True, default="PKR")
    fee_status = Column(Enum(FeeStatus), nullable=True, default=FeeStatus.pending)
    fee_paid_on = Column(Date, nullable=True)
    # Free-text label for "where the money went" — e.g. "Meezan — Qureshi",
    # "JazzCash 0300...", "Cash drawer", etc. Not validated; just for traceability.
    fee_credit_account = Column(String(160), nullable=True)

    student = relationship("Student", back_populates="access_grants")
    folder = relationship("DriveFolder")
    granted_by = relationship("User", foreign_keys=[granted_by_id])

    __table_args__ = (
        Index("ix_grant_student_folder", "student_id", "folder_id"),
    )


class RevenueEvent(Base):
    """Money earned, linked to a student (or null for general income)."""
    __tablename__ = "revenue_events"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="PKR")
    source = Column(String(120), nullable=True)         # e.g. "Monthly fee", "Course A"
    status = Column(Enum(RevenueStatus), nullable=False, default=RevenueStatus.pending)
    received_on = Column(Date, nullable=True)
    due_on = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = relationship("Student", back_populates="revenues")
    distributions = relationship("RevenueDistribution", back_populates="revenue", cascade="all,delete")


class RevenueDistribution(Base):
    """Computed share for one user from one revenue event."""
    __tablename__ = "revenue_distributions"
    id = Column(Integer, primary_key=True)
    revenue_id = Column(Integer, ForeignKey("revenue_events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ratio = Column(Float, nullable=False)        # applied ratio at compute time
    amount = Column(Float, nullable=False)       # amount * ratio
    payout_id = Column(Integer, ForeignKey("payouts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    revenue = relationship("RevenueEvent", back_populates="distributions")
    user = relationship("User")
    payout = relationship("Payout", foreign_keys=[payout_id])


class Payout(Base):
    """A payment made to a user, grouping one or more distributions."""
    __tablename__ = "payouts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    period_label = Column(String(80), nullable=True)   # e.g. "2026-07"
    status = Column(Enum(PayoutStatus), nullable=False, default=PayoutStatus.pending)
    paid_on = Column(Date, nullable=True)
    method = Column(String(80), nullable=True)        # cash, bank, jazzcash...
    reference = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="payouts")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(80), nullable=False)
    target_type = Column(String(60), nullable=True)
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ---------- Engine / Session ----------

_settings = get_settings()
Path(BASE_DIR := _settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def _migrate_schema() -> None:
    """Idempotent column adds for DBs created before the seller/fee iteration.

    SQLite has no `ADD COLUMN IF NOT EXISTS`, so we inspect pragma_table_info
    and only run ALTERs for columns that are genuinely missing. Safe to call
    on every startup.
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        inspector_cols = {
            "access_grants": {row[1] for row in conn.execute(text("PRAGMA table_info(access_grants)")).fetchall()},
        }
    needed = {
        "access_grants": [
            ("price_amount", "FLOAT"),
            ("price_currency", "VARCHAR(8) DEFAULT 'PKR'"),
            ("fee_status", "VARCHAR(16)"),  # enum-as-string; we cast in app layer
            ("fee_paid_on", "DATE"),
            ("fee_credit_account", "VARCHAR(160)"),
        ],
        "drive_folders": [
            ("default_price", "FLOAT"),
            ("default_currency", "VARCHAR(8) DEFAULT 'PKR'"),
        ],
    }
    with engine.begin() as conn:
        for table, adds in needed.items():
            existing = inspector_cols.get(table, set())
            for col, decl in adds:
                if col in existing:
                    continue
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))
                except Exception:
                    # If two workers race, one will fail; the other already added.
                    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
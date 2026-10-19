"""Background jobs — Drive grant expiry cleanup."""
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, AccessGrant, AccessStatus
from .drive import revoke_folder_access, DriveServiceError
from .audit import log


def expire_grants_job() -> None:
    """Mark all grants past expiry, and revoke their Drive permissions."""
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        stale = db.query(AccessGrant).filter(
            AccessGrant.status == AccessStatus.active,
            AccessGrant.expires_at < now,
        ).all()
        if not stale:
            return
        for g in stale:
            if g.drive_permission_id:
                try:
                    revoke_folder_access(
                        drive_folder_id=g.folder.drive_folder_id,
                        permission_id=g.drive_permission_id,
                    )
                except DriveServiceError:
                    # Even if Drive revoke failed, mark expired so we don't keep retrying forever.
                    pass
            g.status = AccessStatus.expired
            g.revoked_at = now
            log(db, action="grant.expire",
                target_type="grant", target_id=g.id,
                detail=f"Auto-expired ({g.student.full_name} → {g.folder.label})")
        db.commit()
    finally:
        db.close()


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    s = BackgroundScheduler(daemon=True, timezone="UTC")
    minutes = get_settings().expiry_job_interval_minutes
    s.add_job(expire_grants_job, "interval", minutes=minutes, id="expire_grants", replace_existing=True)
    s.start()
    _scheduler = s


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
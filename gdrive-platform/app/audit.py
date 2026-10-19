"""Audit log helper."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .db import AuditLog


def log(
    db: Session,
    *,
    action: str,
    actor_user_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    db.add(AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        created_at=datetime.utcnow(),
    ))
    db.flush()
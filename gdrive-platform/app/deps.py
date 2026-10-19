"""FastAPI dependency helpers."""
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .db import User, get_db
from .security import decode_token


COOKIE_NAME = "gdrive_session"


# --- Flash messages ---------------------------------------------------------
# Tiny session-based one-shot messages. We piggyback on the same JWT cookie
# (already httponly+samesite=lax) by re-encoding it with a `flash` claim. That
# keeps us from adding a second cookie / session middleware.
#
# Usage:
#   from .deps import flash
#   flash(request, "Folder not found", level="error")
#   return RedirectResponse("/folders", status_code=303)
#
# In a template:
#   {% set f = pop_flash(request) %}
#   {% if f %}<div class="...">{{ f.msg }}</div>{% endif %}
import json
import base64
import hmac
import hashlib
from typing import Optional


def _flash_key():
    # Reuse the app secret so the cookie stays a single token.
    from .config import get_settings
    return get_settings().app_secret.encode()


def _sign(payload: bytes) -> str:
    return hmac.new(_flash_key(), payload, hashlib.sha256).hexdigest()


def flash(request: Request, message: str, level: str = "info") -> None:
    """Attach a one-shot message to the outgoing response.

    Call this BEFORE returning a RedirectResponse. The actual response
    object returned by the route is what carries the cookie, so we set the
    cookie via a small Response-collector that the route should return.
    See `apply_flash_to_response` for the simplest API.
    """
    if not hasattr(request, "_flash_queue"):
        request._flash_queue = []  # type: ignore[attr-defined]
    request._flash_queue.append({"msg": message, "level": level})


def apply_flash_to_response(request: Request, response: RedirectResponse) -> RedirectResponse:
    """If any flashes were queued, bake them into the response cookie."""
    queue = getattr(request, "_flash_queue", None)
    if not queue:
        return response
    payload = base64.urlsafe_b64encode(json.dumps(queue).encode()).decode().rstrip("=")
    sig = _sign(payload.encode())
    response.set_cookie("gdrive_flash", f"{payload}.{sig}",
                        httponly=False, samesite="lax", max_age=60,
                        path="/")
    return response


def pop_flash(request: Request) -> Optional[dict]:
    raw = request.cookies.get("gdrive_flash")
    if not raw:
        return None
    try:
        payload, sig = raw.rsplit(".", 1)
        if not hmac.compare_digest(_sign(payload.encode()), sig):
            return None
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if isinstance(data, list) and data:
            # Return first; we only ever set one at a time from any single POST.
            return data[0]
    except Exception:
        return None
    return None


# --- Auth dependencies ------------------------------------------------------


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    email = payload.get("sub")
    if not email:
        return None
    user = db.query(User).filter(User.email == email, User.is_active == True).first()  # noqa: E712
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    return user


def require_perm(perm: str):
    from .permissions import can

    def _checker(request: Request, db: Session = Depends(get_db)) -> User:
        user = require_user(request, db)
        if not can(user.role, perm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {perm}")
        return user

    return _checker
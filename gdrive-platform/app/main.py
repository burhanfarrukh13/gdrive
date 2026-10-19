"""FastAPI app entrypoint."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import BASE_DIR, get_settings
from .db import init_db, User, UserRole, get_db
from .security import hash_password
from .permissions import can
from .tpl import templates  # shared Jinja2Templates with globals pre-registered
from .routers import auth as auth_router
from .routers import dashboard as dashboard_router
from .routers import students as students_router
from .routers import folders as folders_router
from .routers import team as team_router
from .routers import finance as finance_router
from .routers import audit as audit_router
from .routers import fees as fees_router
from .jobs import start_scheduler, stop_scheduler


def _seed_admin_if_empty() -> None:
    s = get_settings()
    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        if db.query(User).count() == 0:
            db.add(User(
                full_name=s.bootstrap_admin_name,
                email=s.bootstrap_admin_email,
                password_hash=hash_password(s.bootstrap_admin_password),
                role=UserRole.owner,
                default_ratio=1.0,
                is_active=True,
            ))
            db.commit()
    finally:
        db_gen.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_admin_if_empty()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="Drive Access & Revenue Manager", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "app" / "static")),
    name="static",
)


@app.get("/health")
def health():
    return {"status": "ok"}


# Tiny partial-render helpers (HTMX-style)
@app.get("/partials/nav", response_class=HTMLResponse)
def nav_partial(request: Request):
    from .deps import current_user
    user = current_user(request, next(get_db()))
    return templates.TemplateResponse("partials/nav.html", {
        "request": request, "user": user, "can": can,
    })


# Routers
app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(students_router.router)
app.include_router(folders_router.router)
app.include_router(team_router.router)
app.include_router(finance_router.router)
app.include_router(audit_router.router)
app.include_router(fees_router.router)


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    return HTMLResponse(
        f"<html><body style='font-family:system-ui;background:#0b0f17;color:#e5e7eb;padding:40px'>"
        f"<h1>403 — Forbidden</h1><p>{exc.detail}</p>"
        f"<a href='/dashboard' style='color:#60a5fa'>← back to dashboard</a></body></html>",
        status_code=403,
    )

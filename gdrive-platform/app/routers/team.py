"""Team & roles management."""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..tpl import templates
from ..db import User, UserRole, get_db
from ..deps import require_perm
from ..audit import log
from ..security import hash_password
from ..permissions import can


router = APIRouter()


@router.get("/team", response_class=HTMLResponse)
def team_list(request: Request, db: Session = Depends(get_db), user=Depends(require_perm("team.view"))):
    members = db.query(User).order_by(User.role.asc(), User.full_name.asc()).all()
    total_ratio = round(sum(m.default_ratio for m in members if m.is_active), 4)
    return templates.TemplateResponse("team/list.html", {
        "request": request, "user": user, "members": members,
        "total_ratio": total_ratio, "can": can, "UserRole": UserRole,
    })


@router.post("/team/new")
def create_member(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    default_ratio: float = Form(0.0),
    phone: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("team.create")),
):
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already in use.")
    if default_ratio < 0 or default_ratio > 1:
        raise HTTPException(400, "Ratio must be between 0 and 1.")
    try:
        role_enum = UserRole(role)
    except ValueError:
        raise HTTPException(400, "Invalid role.")
    u = User(
        full_name=full_name.strip(),
        email=email,
        password_hash=hash_password(password),
        role=role_enum,
        default_ratio=default_ratio,
        phone=phone.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(u); db.flush()
    log(db, action="user.create", actor_user_id=user.id, target_type="user", target_id=u.id, detail=f"{u.full_name} <{u.email}> role={u.role.value}")
    db.commit()
    return RedirectResponse("/team", status_code=303)


@router.post("/team/{uid}/update")
def update_member(
    uid: int,
    request: Request,
    full_name: str = Form(...),
    role: str = Form(...),
    default_ratio: float = Form(0.0),
    phone: str = Form(""),
    notes: str = Form(""),
    is_active: str = Form("1"),
    password: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("team.update")),
):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404)
    if u.id == user.id and (is_active != "1" or role != UserRole.owner.value):
        raise HTTPException(400, "You cannot demote or deactivate yourself.")
    if default_ratio < 0 or default_ratio > 1:
        raise HTTPException(400, "Ratio must be between 0 and 1.")
    u.full_name = full_name.strip()
    u.role = UserRole(role)
    u.default_ratio = default_ratio
    u.phone = phone.strip() or None
    u.notes = notes.strip() or None
    u.is_active = is_active == "1"
    if password:
        u.password_hash = hash_password(password)
    log(db, action="user.update", actor_user_id=user.id, target_type="user", target_id=u.id)
    db.commit()
    return RedirectResponse("/team", status_code=303)


@router.post("/team/{uid}/delete")
def delete_member(uid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("team.delete"))):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404)
    if u.id == user.id:
        raise HTTPException(400, "Cannot delete yourself.")
    log(db, action="user.delete", actor_user_id=user.id, target_type="user", target_id=u.id, detail=u.full_name)
    db.delete(u); db.commit()
    return RedirectResponse("/team", status_code=303)

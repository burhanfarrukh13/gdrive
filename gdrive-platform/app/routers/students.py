"""Students CRUD + search."""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..tpl import templates
from ..db import Student, DriveFolder, get_db
from ..deps import require_perm
from ..audit import log
from ..permissions import can


router = APIRouter()


@router.get("/students", response_class=HTMLResponse)
def list_students(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_perm("students.view")),
):
    query = db.query(Student)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Student.full_name.ilike(like),
            Student.email.ilike(like),
            Student.google_email.ilike(like),
            Student.course_or_batch.ilike(like),
        ))
    students = query.order_by(Student.full_name.asc()).all()
    return templates.TemplateResponse("students/list.html", {
        "request": request, "user": user, "students": students, "q": q, "can": can,
    })


@router.get("/students/new", response_class=HTMLResponse)
def new_form(request: Request, db: Session = Depends(get_db), user=Depends(require_perm("students.create"))):
    return templates.TemplateResponse("students/form.html", {
        "request": request, "user": user, "student": None, "can": can,
    })


@router.post("/students/new")
def create_student(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    google_email: str = Form(...),
    phone: str = Form(""),
    course_or_batch: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("students.create")),
):
    s = Student(
        full_name=full_name.strip(),
        email=email.strip().lower(),
        google_email=google_email.strip().lower(),
        phone=phone.strip() or None,
        course_or_batch=course_or_batch.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(s); db.flush()
    log(db, action="student.create", actor_user_id=user.id, target_type="student", target_id=s.id, detail=f"{s.full_name} <{s.email}>")
    db.commit()
    return RedirectResponse(f"/students/{s.id}", status_code=303)


@router.get("/students/{sid}", response_class=HTMLResponse)
def student_detail(sid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("students.view"))):
    s = db.query(Student).filter(Student.id == sid).first()
    if not s:
        raise HTTPException(404, "Student not found")
    grants = sorted(s.access_grants, key=lambda g: g.expires_at, reverse=True)
    revenues = sorted(s.revenues, key=lambda r: r.created_at, reverse=True)
    all_folders = db.query(DriveFolder).filter(DriveFolder.is_archived == False).order_by(DriveFolder.label).all()  # noqa: E712

    # Fee totals for the header strip on this student's grant list.
    fee_totals = {"pending": "—", "paid": "—", "waived": ""}
    priced = [g for g in grants if g.price_amount and g.price_amount > 0]
    if priced:
        from collections import defaultdict
        sums = defaultdict(float)
        for g in priced:
            key = g.fee_status.value if g.fee_status else "pending"
            sums[key] += float(g.price_amount)
        for k in ("pending", "paid", "waived"):
            if sums.get(k):
                fee_totals[k] = f"{sums[k]:.0f}"

    return templates.TemplateResponse("students/detail.html", {
        "request": request, "user": user, "student": s, "grants": grants, "revenues": revenues,
        "all_folders": all_folders, "fee_totals": fee_totals, "can": can,
    })


@router.get("/students/{sid}/edit", response_class=HTMLResponse)
def edit_form(sid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("students.update"))):
    s = db.query(Student).filter(Student.id == sid).first()
    if not s:
        raise HTTPException(404, "Student not found")
    return templates.TemplateResponse("students/form.html", {
        "request": request, "user": user, "student": s, "can": can,
    })


@router.post("/students/{sid}/edit")
def update_student(
    sid: int,
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    google_email: str = Form(...),
    phone: str = Form(""),
    course_or_batch: str = Form(""),
    notes: str = Form(""),
    is_active: str = Form("1"),
    db: Session = Depends(get_db),
    user=Depends(require_perm("students.update")),
):
    s = db.query(Student).filter(Student.id == sid).first()
    if not s:
        raise HTTPException(404, "Student not found")
    s.full_name = full_name.strip()
    s.email = email.strip().lower()
    s.google_email = google_email.strip().lower()
    s.phone = phone.strip() or None
    s.course_or_batch = course_or_batch.strip() or None
    s.notes = notes.strip() or None
    s.is_active = is_active == "1"
    s.updated_at = datetime.utcnow()
    log(db, action="student.update", actor_user_id=user.id, target_type="student", target_id=s.id)
    db.commit()
    return RedirectResponse(f"/students/{s.id}", status_code=303)


@router.post("/students/{sid}/delete")
def delete_student(sid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("students.delete"))):
    s = db.query(Student).filter(Student.id == sid).first()
    if not s:
        raise HTTPException(404)
    log(db, action="student.delete", actor_user_id=user.id, target_type="student", target_id=s.id, detail=s.full_name)
    db.delete(s); db.commit()
    return RedirectResponse("/students", status_code=303)

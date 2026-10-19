"""Folders registry + access grants."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..tpl import templates
from ..db import (
    DriveFolder, Student, AccessGrant, AccessStatus, FeeStatus, get_db,
)
from ..deps import require_perm, flash, apply_flash_to_response
from ..audit import log
from ..drive import (
    DriveServiceError, is_configured as drive_is_configured,
    verify_folder, grant_folder_access, revoke_folder_access, disable_folder_copy_print,
    extract_folder_id,
)
from ..permissions import can
from ..distribution import sync_revenue_for_grant


router = APIRouter()


# -------- Folders --------

@router.get("/folders", response_class=HTMLResponse)
def list_folders(
    request: Request,
    q: str = "",
    show_archived: str = "0",
    db: Session = Depends(get_db),
    user=Depends(require_perm("folders.view")),
):
    query = db.query(DriveFolder)
    if show_archived != "1":
        query = query.filter(DriveFolder.is_archived == False)  # noqa: E712
    if q:
        query = query.filter(or_(
            DriveFolder.label.ilike(f"%{q}%"),
            DriveFolder.drive_folder_id.ilike(f"%{q}%"),
        ))
    folders = query.order_by(DriveFolder.label.asc()).all()
    active_grant_rows = db.query(AccessGrant.folder_id, AccessGrant.id).filter(
        AccessGrant.status == AccessStatus.active
    ).all()
    grant_counts = {}
    for folder_id, _ in active_grant_rows:
        grant_counts[folder_id] = grant_counts.get(folder_id, 0) + 1
    return templates.TemplateResponse("folders/list.html", {
        "request": request, "user": user, "folders": folders, "q": q,
        "show_archived": show_archived, "drive_ready": drive_is_configured(),
        "grant_counts": grant_counts, "can": can,
    })


@router.post("/folders/new")
def create_folder(
    request: Request,
    label: str = Form(...),
    drive_folder_id: str = Form(...),
    description: str = Form(""),
    default_price: str = Form("0"),
    default_currency: str = Form("PKR"),
    db: Session = Depends(get_db),
    user=Depends(require_perm("folders.create")),
):
    fid = extract_folder_id(drive_folder_id)

    existing = db.query(DriveFolder).filter(DriveFolder.drive_folder_id == fid).first()
    if existing:
        flash(request,
              f"\"{existing.label}\" is already registered with this folder. "
              "Edit or archive that entry instead.",
              level="warn")
        return apply_flash_to_response(request, RedirectResponse("/folders", status_code=303))

    try:
        meta = verify_folder(fid)
    except DriveServiceError as e:
        flash(request, f"Drive rejected the folder: {e}", level="error")
        return apply_flash_to_response(request, RedirectResponse("/folders", status_code=303))
    try:
        dp = float(default_price) if default_price not in (None, "") else 0.0
        if dp < 0:
            raise ValueError
    except ValueError:
        flash(request, "Default price must be a non-negative number.", level="error")
        return apply_flash_to_response(request, RedirectResponse("/folders", status_code=303))
    folder = DriveFolder(
        label=label.strip(),
        drive_folder_id=fid,
        drive_owner_email=(meta.get("owners") or [{}])[0].get("emailAddress"),
        description=description.strip() or None,
        default_price=dp if dp > 0 else None,
        default_currency=(default_currency or "PKR").strip().upper()[:8] or "PKR",
    )
    db.add(folder); db.flush()
    # Best-effort: turn off copy/print for viewers
    try:
        disable_folder_copy_print(fid)
    except Exception:
        pass
    log(db, action="folder.create", actor_user_id=user.id, target_type="folder", target_id=folder.id, detail=folder.label)
    db.commit()
    flash(request, f"Folder \"{folder.label}\" added.", level="success")
    return apply_flash_to_response(request, RedirectResponse("/folders", status_code=303))


@router.post("/folders/{fid}/default-price")
def update_default_price(
    fid: int,
    request: Request,
    default_price: str = Form(""),
    default_currency: str = Form("PKR"),
    db: Session = Depends(get_db),
    user=Depends(require_perm("folders.update")),
):
    f = db.query(DriveFolder).filter(DriveFolder.id == fid).first()
    if not f:
        raise HTTPException(404)
    try:
        dp = float(default_price) if default_price not in (None, "") else 0.0
        if dp < 0:
            raise ValueError
    except ValueError:
        flash(request, "Default price must be a non-negative number.", level="error")
        return apply_flash_to_response(request, RedirectResponse("/folders", status_code=303))
    f.default_price = dp if dp > 0 else None
    f.default_currency = (default_currency or "PKR").strip().upper()[:8] or "PKR"
    log(db, action="folder.default_price", actor_user_id=user.id, target_type="folder",
        target_id=f.id, detail=f"{f.label} -> {f.default_price or 0} {f.default_currency}")
    db.commit()
    flash(request, f"Default price for \"{f.label}\" set to {f.default_price or 0} {f.default_currency}.", level="success")
    return apply_flash_to_response(request, RedirectResponse("/folders", status_code=303))


@router.post("/folders/{fid}/archive")
def archive_folder(fid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("folders.update"))):
    f = db.query(DriveFolder).filter(DriveFolder.id == fid).first()
    if not f:
        raise HTTPException(404)
    f.is_archived = not f.is_archived
    log(db, action="folder.archive" if f.is_archived else "folder.unarchive",
        actor_user_id=user.id, target_type="folder", target_id=f.id)
    db.commit()
    return RedirectResponse("/folders", status_code=303)


# -------- Grants --------

@router.get("/grants", response_class=HTMLResponse)
def list_grants(
    request: Request,
    status_filter: str = "active",
    student_id: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_perm("grants.view")),
):
    student_id_int: int | None = int(student_id) if student_id.strip().isdigit() else None
    q = db.query(AccessGrant).join(Student).join(DriveFolder)
    if status_filter != "all":
        q = q.filter(AccessGrant.status == AccessStatus(status_filter))
    if student_id_int:
        q = q.filter(AccessGrant.student_id == student_id_int)
    grants = q.order_by(AccessGrant.expires_at.asc()).all()
    students = db.query(Student).filter(Student.is_active == True).order_by(Student.full_name).all()  # noqa: E712
    folders = db.query(DriveFolder).filter(DriveFolder.is_archived == False).order_by(DriveFolder.label).all()  # noqa: E712
    return templates.TemplateResponse("grants/list.html", {
        "request": request, "user": user, "grants": grants, "students": students,
        "folders": folders, "status_filter": status_filter,
        "student_id": student_id_int, "drive_ready": drive_is_configured(), "can": can,
    })


@router.post("/grants/new")
def create_grant(
    request: Request,
    student_id: int = Form(...),
    folder_ids: list[int] = Form(...),
    days: int = Form(...),
    notes: str = Form(""),
    # --- Fee fields (added with the seller role) ---
    price_amount: str = Form("0"),
    price_currency: str = Form("PKR"),
    fee_status: str = Form("pending"),
    fee_credit_account: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_perm("grants.create")),
):
    if days < 1 or days > 365:
        flash(request, "Expiry must be between 1 and 365 days.", level="error")
        return apply_flash_to_response(request, RedirectResponse(f"/students/{student_id}", status_code=303))
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        flash(request, "Student not found.", level="error")
        return apply_flash_to_response(request, RedirectResponse("/students", status_code=303))

    # Parse fee inputs safely.
    try:
        price_value = float(price_amount) if price_amount not in (None, "") else 0.0
        if price_value < 0:
            raise ValueError
    except ValueError:
        flash(request, "Price must be a non-negative number.", level="error")
        return apply_flash_to_response(request, RedirectResponse(f"/students/{student_id}", status_code=303))

    try:
        fee_enum = FeeStatus(fee_status)
    except ValueError:
        fee_enum = FeeStatus.pending

    currency = (price_currency or "PKR").strip().upper()[:8] or "PKR"
    credit_to = fee_credit_account.strip()[:160] or None

    expires_at = datetime.utcnow() + timedelta(days=days)
    created = []
    errors = []

    for fid in folder_ids:
        folder = db.query(DriveFolder).filter(DriveFolder.id == fid).first()
        if not folder:
            continue
        # Skip if an active grant already exists for this pair; we'll just extend it.
        existing = db.query(AccessGrant).filter(
            AccessGrant.student_id == student_id,
            AccessGrant.folder_id == fid,
            AccessGrant.status == AccessStatus.active,
        ).first()
        try:
            perm = grant_folder_access(
                drive_folder_id=folder.drive_folder_id,
                google_email=student.google_email,
                expires_at=expires_at,
            )
        except DriveServiceError as e:
            errors.append(f"{folder.label}: {e}")
            continue

        if existing:
            existing.expires_at = expires_at
            existing.drive_permission_id = perm.get("id") or existing.drive_permission_id
            existing.granted_by_id = user.id
            existing.granted_at = datetime.utcnow()
            existing.notes = notes or existing.notes
            # Update fee fields only if the user supplied a non-zero price;
            # otherwise leave existing fee data alone.
            if price_value > 0:
                existing.price_amount = price_value
                existing.price_currency = currency
                existing.fee_status = fee_enum
                existing.fee_credit_account = credit_to or existing.fee_credit_account
            sync_revenue_for_grant(db, existing)
            log(db, action="grant.extend", actor_user_id=user.id,
                target_type="grant", target_id=existing.id,
                detail=f"{student.full_name} → {folder.label} (+{days}d)")
            created.append(existing)
        else:
            g = AccessGrant(
                student_id=student_id,
                folder_id=fid,
                expires_at=expires_at,
                granted_by_id=user.id,
                drive_permission_id=perm.get("id"),
                notes=notes or None,
                price_amount=price_value if price_value > 0 else None,
                price_currency=currency,
                fee_status=fee_enum,
                fee_credit_account=credit_to,
            )
            db.add(g); db.flush()
            sync_revenue_for_grant(db, g)
            log(db, action="grant.create", actor_user_id=user.id,
                target_type="grant", target_id=g.id,
                detail=f"{student.full_name} → {folder.label} ({days}d, {price_value} {currency}, {fee_enum.value})")
            created.append(g)

    db.commit()

    if errors and not created:
        flash(request, "All grants failed: " + " | ".join(errors), level="error")
        return apply_flash_to_response(request, RedirectResponse(f"/students/{student_id}", status_code=303))
    if errors:
        flash(request, "Some grants failed: " + " | ".join(errors), level="warn")
        return apply_flash_to_response(request, RedirectResponse(f"/students/{student_id}", status_code=303))
    flash(request,
          f"Granted {len(created)} folder{'s' if len(created) != 1 else ''} to {student.full_name} "
          f"for {days} day{'s' if days != 1 else ''}.",
          level="success")
    return apply_flash_to_response(request, RedirectResponse(f"/students/{student_id}", status_code=303))


@router.post("/grants/{gid}/revoke")
def revoke_grant(gid: int, request: Request, db: Session = Depends(get_db), user=Depends(require_perm("grants.revoke"))):
    g = db.query(AccessGrant).filter(AccessGrant.id == gid).first()
    if not g:
        raise HTTPException(404)
    if g.status != AccessStatus.active:
        return RedirectResponse("/grants", status_code=303)
    if g.drive_permission_id:
        try:
            revoke_folder_access(
                drive_folder_id=g.folder.drive_folder_id,
                permission_id=g.drive_permission_id,
            )
        except DriveServiceError as e:
            flash(request, f"Drive error while revoking: {e}", level="error")
            return apply_flash_to_response(
                request,
                RedirectResponse(request.headers.get("referer", "/grants"), status_code=303),
            )
    g.status = AccessStatus.revoked
    g.revoked_at = datetime.utcnow()
    log(db, action="grant.revoke", actor_user_id=user.id, target_type="grant", target_id=g.id)
    db.commit()
    flash(request, f"Revoked access to \"{g.folder.label}\" for {g.student.full_name}.", level="success")
    return apply_flash_to_response(
        request,
        RedirectResponse(request.headers.get("referer", "/grants"), status_code=303),
    )

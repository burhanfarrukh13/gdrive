"""Google Drive service.

Wraps the small set of operations we need:
  - verify a folder ID exists and is reachable
  - grant a time-bound, view-only permission to a Google account
  - revoke a permission

Uses a Service Account. Folders must be shared with the SA at Editor
level for the main Drive (one-time setup).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from .config import get_settings


SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveServiceError(Exception):
    pass


def _build_service():
    settings = get_settings()
    key_path = Path(settings.google_service_account_file)
    if not key_path.is_absolute():
        key_path = Path(__file__).resolve().parent.parent / key_path

    if not key_path.exists():
        raise DriveServiceError(
            f"Service account key not found at {key_path}. "
            "Place your downloaded JSON there, or set GOOGLE_SERVICE_ACCOUNT_FILE in .env."
        )

    creds = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=SCOPES
    )
    # Impersonate the workspace domain user if provided.
    if settings.google_workspace_domain:
        creds = creds.with_subject(settings.google_workspace_domain)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


_svc = None


def service():
    global _svc
    if _svc is None:
        _svc = _build_service()
    return _svc


def is_configured() -> bool:
    settings = get_settings()
    p = Path(settings.google_service_account_file)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    return p.exists()


def extract_folder_id(raw: str) -> str:
    """Accept a bare folder ID or any common Drive folder URL and return
    just the ID.

    Handles:
      - plain ID:                      1AbCdefXyz123
      - .../drive/folders/<id>         (optionally with /u/0/ and any ?query)
      - .../open?id=<id>
      - ...?id=<id>  (anywhere in the query string)
    """
    raw = raw.strip()
    if not raw:
        return raw

    # .../folders/<id>[/...][?...]
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", raw)
    if m:
        return m.group(1)

    # ...?id=<id> or &id=<id>
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", raw)
    if m:
        return m.group(1)

    # Already looks like a bare ID (no slashes/colons) — strip stray query string if any.
    if "://" not in raw and "/" not in raw:
        return raw.split("?")[0]

    # Fallback: last path segment, query stripped.
    last_segment = raw.rstrip("/").split("/")[-1]
    return last_segment.split("?")[0]


def verify_folder(drive_folder_id: str) -> dict:
    """Return folder metadata or raise DriveServiceError."""
    try:
        meta = service().files().get(
            fileId=drive_folder_id,
            fields="id,name,mimeType,owners,webViewLink,permissions",
            supportsAllDrives=True,
        ).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            raise DriveServiceError(f"ID {drive_folder_id} is not a folder.")
        return meta
    except HttpError as e:
        raise DriveServiceError(_friendly_http_error(e)) from e


def grant_folder_access(
    *,
    drive_folder_id: str,
    google_email: str,
    expires_at: datetime,
    permission_id_to_replace: Optional[str] = None,
) -> dict:
    """Grant a view-only permission for a student's Google account.

    NOTE: we deliberately do NOT set Drive's native `expirationTime` here.
    Google only allows the file *owner* to create/update a permission that
    carries an expiration date — a service account holding Editor (but not
    ownership) on a personally-owned My Drive folder gets a 403 trying to
    do this, even though it has full write access otherwise. Since our
    folders are owned by the client's personal Google account (not a
    Shared Drive the bot organizes), we can't set native expiration.

    Instead, `expires_at` is tracked only in our own database, and the
    background job in jobs.py (`expire_grants_job`) revokes the Drive
    permission once it's past due. This sidesteps the ownership
    restriction entirely — role=reader + no expirationTime is something
    any Editor can create.
    """
    body = {
        "type": "user",
        "role": "reader",
        "emailAddress": google_email,
    }
    try:
        if permission_id_to_replace:
            return service().permissions().update(
                fileId=drive_folder_id,
                permissionId=permission_id_to_replace,
                body=body,
                sendNotificationEmail=False,
                supportsAllDrives=True,
                useDomainAdminAccess=False,
            ).execute()
        return service().permissions().create(
            fileId=drive_folder_id,
            body=body,
            sendNotificationEmail=False,
            supportsAllDrives=True,
            useDomainAdminAccess=False,
        ).execute()
    except HttpError as e:
        raise DriveServiceError(_friendly_http_error(e)) from e


def revoke_folder_access(*, drive_folder_id: str, permission_id: str) -> None:
    try:
        service().permissions().delete(
            fileId=drive_folder_id,
            permissionId=permission_id,
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        raise DriveServiceError(_friendly_http_error(e)) from e


def disable_folder_copy_print(drive_folder_id: str) -> None:
    """Set viewersCanCopyContent=False on the folder. Best-effort."""
    try:
        service().files().update(
            fileId=drive_folder_id,
            body={"viewersCanCopyContent": False},
            supportsAllDrives=True,
        ).execute()
    except HttpError:
        # Older files/folders may not support this — ignore.
        pass


def _friendly_http_error(e: HttpError) -> str:
    try:
        status = e.resp.status
        reason = e._get_reason()
    except Exception:
        return str(e)
    if status == 404:
        return "Folder not found or service account has no access. Did you share the folder with the service account email at Editor level?"
    if status == 403:
        return (
            "Permission denied. Either the service account lacks Editor access to "
            "this folder, or (if this happened while granting access) Google "
            "blocked an expiration date on a permission for a folder it doesn't own."
        )
    return f"Drive API error {status}: {reason}"
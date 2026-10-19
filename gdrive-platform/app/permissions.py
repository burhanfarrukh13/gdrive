"""Role-based permissions used across the admin UI.

Single source of truth — every page/route asks `can(user, "students.create")`.
"""
from .db import UserRole


# Permission -> set of roles that have it
PERMISSIONS: dict[str, set[UserRole]] = {
    # Dashboard
    "dashboard.view": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.accountant, UserRole.viewer},

    # Students
    "students.view": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.accountant, UserRole.seller, UserRole.viewer},
    "students.create": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.seller},
    "students.update": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.seller},
    "students.delete": {UserRole.owner, UserRole.admin},

    # Folders
    "folders.view": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.seller, UserRole.viewer},
    "folders.create": {UserRole.owner, UserRole.admin, UserRole.manager},
    "folders.update": {UserRole.owner, UserRole.admin, UserRole.manager},
    "folders.delete": {UserRole.owner, UserRole.admin},

    # Access grants
    "grants.view": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.accountant, UserRole.seller, UserRole.viewer},
    "grants.create": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.seller},
    "grants.revoke": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.seller},

    # Fees (per-grant price + payment tracking). Sellers can VIEW their own sales
    # (enforced in router by filtering on granted_by_id); marking paid requires
    # fees.update which is manager+.
    "fees.view": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.accountant, UserRole.seller},
    "fees.update": {UserRole.owner, UserRole.admin, UserRole.manager},

    # Team & roles
    "team.view": {UserRole.owner, UserRole.admin, UserRole.accountant, UserRole.viewer},
    "team.create": {UserRole.owner, UserRole.admin},
    "team.update": {UserRole.owner, UserRole.admin},
    "team.delete": {UserRole.owner},
    "team.edit_ratios": {UserRole.owner},

    # Revenue
    "revenue.view": {UserRole.owner, UserRole.admin, UserRole.manager, UserRole.accountant},
    "revenue.create": {UserRole.owner, UserRole.admin, UserRole.accountant},
    "revenue.update": {UserRole.owner, UserRole.admin, UserRole.accountant},
    "revenue.delete": {UserRole.owner, UserRole.admin},

    # Payouts
    "payouts.view": {UserRole.owner, UserRole.admin, UserRole.accountant},
    "payouts.create": {UserRole.owner, UserRole.admin, UserRole.accountant},
    "payouts.update": {UserRole.owner, UserRole.admin},

    # Audit
    "audit.view": {UserRole.owner, UserRole.admin},

    # Settings
    "settings.view": {UserRole.owner, UserRole.admin},
    "settings.update": {UserRole.owner},
}


def can(role: UserRole | str | None, permission: str) -> bool:
    if role is None:
        return False
    if isinstance(role, str):
        try:
            role = UserRole(role)
        except ValueError:
            return False
    allowed = PERMISSIONS.get(permission, set())
    return role in allowed


def require_any(role: UserRole | str | None, *permissions: str) -> bool:
    return any(can(role, p) for p in permissions)
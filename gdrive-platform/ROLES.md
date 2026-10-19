# Roles & Permissions Guide

This document describes the six roles in the Drive Access & Revenue Manager, what each one can do, and the day-to-day workflow for the people holding them.

> **Single source of truth**: `app/permissions.py`. The matrix below is generated from that file — if you change permissions in code, update this doc in the same commit.

---

## The 6 roles at a glance

| Role | One-line | Created by |
|---|---|---|
| `owner` | Full access. The founder / single point of control. Can change anyone's role, edit share ratios, see the audit log. | Bootstrap (first run) |
| `admin` | Full operational access. Everything except editing share ratios. Useful for a co-founder or operations lead. | owner |
| `manager` | Owns the customer-facing workflow: students, folders, grants, fees. Can also view revenue. Does **not** create revenue events directly (they come from sales). | owner / admin |
| `accountant` | Owns the money side: revenue distributions, payouts, team balances. Read-only on the rest. | owner / admin |
| `seller` | **Front-line sales.** Adds new students, sells access with a price. Can view fees for sales they personally made. Cannot mark fees paid (that's a manager call). Cannot touch folders, revenue, payouts, or the team. | owner / admin |
| `viewer` | Read-only across the board. | owner / admin |

---

## Full permission matrix

✅ = allowed · ❌ = denied

| Permission | owner | admin | manager | accountant | seller | viewer |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| **Dashboard** | | | | | | |
| `dashboard.view` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Students** | | | | | | |
| `students.view` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `students.create` | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `students.update` | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `students.delete` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Drive folders** | | | | | | |
| `folders.view` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `folders.create` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `folders.update` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `folders.delete` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Access grants** | | | | | | |
| `grants.view` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `grants.create` | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `grants.revoke` | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| **Fees (per-grant)** | | | | | | |
| `fees.view` | ✅ | ✅ | ✅ | ✅ | ✅¹ | ❌ |
| `fees.update` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Revenue** | | | | | | |
| `revenue.view` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `revenue.update` | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| `revenue.delete` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Payouts** | | | | | | |
| `payouts.view` | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| `payouts.create` | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| `payouts.update` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Team & roles** | | | | | | |
| `team.view` | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |
| `team.create` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `team.update` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `team.delete` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `team.edit_ratios` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Audit log** | | | | | | |
| `audit.view` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Settings** | | | | | | |
| `settings.view` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `settings.update` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

¹ Sellers see **only the fees for grants they themselves created** — the `/fees` page filters by `granted_by_id = current_user.id` when the role is `seller`. Managers+ see everything.

> Note on `revenue.create`: there is no longer a standalone "Record new revenue" page. New revenue always comes from a fee on a student sale. See "The unified model" below.

---

## The unified model: fees = revenue

Until recently, fees and revenue were two separate ledgers. They're not anymore. The model is now:

> **A fee on an AccessGrant IS revenue. They are the same thing viewed two ways.**

- The fee fields (`price_amount`, `fee_status`, `fee_paid_on`, `fee_credit_account`) live on the `AccessGrant` row — the sale.
- A `RevenueEvent` row is auto-created/updated from those fields every time the fee changes. It's tagged with `source='fee'` and the grant's ID in its notes.
- The dashboard's "Revenue" tile, the `/revenue` list, and the payouts engine all read from those events.
- Marking a fee paid flips both the grant's `fee_status` AND the linked revenue event in one click.
- Waiving a fee cancels the revenue event (status → cancelled) so totals stay honest.
- The old "Record new" form on `/revenue` redirects to `/students` — you can't add orphan revenue anymore.

**General income** (e.g. a one-off donation, a sponsorship) is the only kind of revenue that doesn't come from a grant. You can still add it directly via the legacy `POST /revenue/{id}/receive` flow, but the typical case is the unified one.

### Why this matters

- **One source of truth.** If you sell a course for 2000 PKR and it shows as pending, the dashboard's receivable tile, the revenue page, and the student's profile all say 2000. They can't drift.
- **The seller doesn't need a separate "record a sale" step.** Selling access IS recording the sale. The Drive permission and the revenue event come from the same form.
- **The manager doesn't need a separate "received a payment" step.** Marking the fee paid IS receiving the revenue. Distribution calculation fires automatically.

---

## What each role actually does day-to-day

### Owner (Qureshi Sahib / you)
- Everything. The only one who can edit share ratios, delete team members, or change settings.
- First account created automatically on first run (`admin@driveaccess.local` / `admin123` from `.env`). **Change the password on first login.**
- Should rarely be needed for day-to-day work — delegate to admin / manager.

### Admin (co-founder, ops lead)
- Every operational task: students, folders, grants, revenue, payouts, team management.
- **Cannot** change share ratios (that's an owner-only knob) or delete the owner account.
- Use this for your second-in-command so you're not the only one with full access.

### Manager (operations / customer success)
- Registers Drive folders, manages the student list, grants and revokes access.
- Marks fees as paid when money comes in. Records which account the money went to.
- Can view revenue but cannot create it (a sale on the student page creates it).
- **Typical daily tasks:**
  - Add a new student who paid on the website
  - Grant that student access to one or more folders, recording the price
  - When payment clears, mark the fee paid + record the credited-to account
  - Archive folders that are no longer being sold

### Accountant (bookkeeper)
- Records general income (e.g. sponsorships), reviews revenue distributions, builds payouts, marks payouts paid.
- Read-only on students, folders, grants, fees. They should be able to see the *what* but never the *who* in a way that lets them touch the customer pipeline.
- **Typical daily tasks:**
  - Reconcile bank statement against the revenue list on `/revenue`
  - Mark received ones (only general income — sales-driven revenue auto-fires when the manager marks the fee paid), which auto-computes per-team-member distributions
  - Build end-of-month payouts
  - Mark payouts paid and record method/reference

### Seller (front-line sales)
- The person who actually closes the deal. Adds a new student when they sign up, then grants them access with the price they agreed on.
- **Cannot** add or manage folders (you set those up once), cannot mark fees as paid (they don't handle the money), cannot touch revenue, payouts, or the team.
- Sees their own sales on the `/fees` page — useful for tracking their own outstanding balances, but not other sellers' books.
- **Typical daily tasks:**
  - A student WhatsApps asking for a course → seller adds them on `/students/new`
  - Seller opens the student's page, clicks "Sell access", picks the folder, enters the price and currency, sets fee status to "Pending" (or "Paid" if the student paid in cash on the spot)
  - The Drive permission is created in the background AND the revenue event is logged. Student gets an email and can open the folder.
  - Later, when the manager sees the payment hit the bank, they mark the fee paid.

### Viewer (read-only auditor)
- Sees everything they have permission to see, but cannot change anything.
- Good for board members, investors, or external auditors who need visibility but should not be one wrong click away from revoking a student's access.

---

## Granting access to a student — the new flow

The "Sell access" button (on a student page) is the single entry point for a sale. It captures:

1. **Folder** — single-select dropdown. If the folder has a default price, the price field pre-fills when you pick it.
2. **Days** — 1 to 365, how long access lasts.
3. **Price** — what the student is paying for this access. Set to 0 for free comps (or use the "Waived" status which locks it at 0).
4. **Currency** — defaults to PKR, change as needed.
5. **Fee status**:
   - `Pending` — student agreed to pay but hasn't yet (default).
   - `Paid` — money already in (useful for cash on delivery or paid in advance).
   - `Waived` — no charge (free comp, review copy, etc.). Price field locks at 0.
6. **Credited to** — free-text label of which account the money should land in, e.g. "Meezan — Qureshi", "JazzCash 03001234567", "Cash drawer". Just a name, no account numbers stored.

The Drive permission AND the matching revenue event are created in one submit. The student gets a viewer-only permission on the folder immediately, and the revenue event is in `pending` (or `received` if you marked it paid at sale time).

### Marking a fee paid

On `/fees` (now called "Sales & Revenue"), find the row and click **Mark paid**. You'll be asked for:

- **Paid on** (date)
- **Credited to** (account/wallet name) — pre-filled if you set it during grant creation, edit if the money went somewhere different

The status flips to `Paid` on the grant, the date is recorded, the credit-account label is locked in, and the linked revenue event flips to `received` automatically. Distribution calculation fires immediately. The row stays visible forever (audit-friendly).

### Waiving a fee

For free comps, set fee status to `Waived` at grant time. If you change your mind later, you can waive an existing pending fee from `/fees` with an optional reason that gets saved to the grant's notes. The linked revenue event flips to `cancelled`.

### Editing a fee

If you typoed the price or the credit account, hit **Set price / Edit** on the row. This writes an audit log entry but does not change the status (so editing a Paid fee does not un-pay it). The linked revenue event's amount is updated.

### Editing a folder's default price

The Folders page has an inline editor for each folder's default price. When set, the "Sell access" modal pre-fills that price when you pick the folder. Per-sale overrides still work.

---

## Sellers seeing only their own data

The `/fees` page is filtered by `granted_by_id` when the logged-in user has role `seller`. The student list on `/students` is **not** filtered — sellers can see all students, they just can't edit the ones they didn't add (well, technically they can `update` — but the audit log captures the change, so it's traceable).

If you want to harden that, edit `app/permissions.py` to split `students.update` into `students.update.own` vs `students.update.any`, and add a row-level check in the update route. We left it permissive for now because the typical case is "I added a student, I'm the only one who touches their record".

---

## Changing a user's role

1. Log in as `owner` or `admin`.
2. Go to `/team`.
3. Find the member, change the role dropdown, hit **Save**.
4. The change takes effect on their next request (their JWT carries the role; it'll refresh on next login or after 12 hours).

You cannot demote or deactivate yourself — the app blocks that. Ask another owner/admin.

---

## What sellers CANNOT do (quick reference)

To make sure nobody on the team is surprised:

- ❌ Add or change Drive folders (one-time setup, owner/manager only)
- ❌ Mark a fee as paid (they don't handle the money)
- ❌ Edit prices after the fact (manager+ can via `/fees` Edit)
- ❌ Delete students
- ❌ See revenue, payouts, or the team list
- ❌ Change their own role

If a seller says "I need to mark this fee paid", that's a sign the workflow needs the manager involved. Don't bend the permissions — keep the money trail clean.

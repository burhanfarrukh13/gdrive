# Drive Access & Revenue Manager

A single-tenant FastAPI platform for a Drive-based coaching/lectures business:

- **Drive Access Control** — register Drive folders, grant students time-bound (1–365 days) view-only access, auto-revoke on expiry, full audit trail.
- **Sales = Revenue** — every student access grant is a sale, and the price attached to it is the revenue. Mark the fee paid and the revenue flips to received in one click.
- **Profit Sharing** — each team member has a share ratio; every received sale is split into per-member distributions.
- **Payouts** — group pending distributions into payouts, mark paid, keep history.
- **Team & Roles** — owner / admin / manager / accountant / seller / viewer with permission-controlled UI.
- **Dashboard** — tiles + charts: revenue trend (14 days), top receivables, team balances, expiring grants, fee totals.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2, SQLite (single-file DB)
- Jinja2 templates + Tailwind CDN + Chart.js + HTMX
- Google Drive API v3 via **Service Account**
- APScheduler for the expiry-cleanup background job

## Quick start

```bash
# 1) Install
pip install -r requirements.txt

# 2) Configure
cp .env.example .env
# (edit APP_SECRET and DATABASE_URL if you want)

# 3) Add your Google Service Account JSON
# Drop the file at: secrets/service_account.json
# (See GOOGLE_SETUP.md for how to get this file.)

# 4) Run
python run.py
# -> http://localhost:8000
# -> login: admin@driveaccess.local / admin123   (change immediately!)
```

The first request auto-creates the SQLite DB at `data/app.db` and seeds the owner. Everything else starts empty — add folders, then students, then sell.

## Roles & permissions

| Role | One-line |
|---|---|
| `owner` | Full access. Can change anyone's role, edit share ratios, see the audit log. |
| `admin` | Full operational access. Cannot edit role structure. |
| `manager` | Customers + folders + grants + fees + can mark fees paid. Can view revenue. |
| `accountant` | Revenue + payouts. Read-only on the rest. |
| `seller` | Front-line sales. Adds students, sells access, records the price. Sees their own sales. Cannot mark fees paid, cannot manage folders, cannot touch revenue/payouts/team. |
| `viewer` | Read-only. |

Full matrix in [ROLES.md](./ROLES.md). Edit the matrix in `app/permissions.py`.

## The one workflow you need to remember

> **Fees and revenue are the same thing.** A fee on a student sale IS revenue. Marking a fee paid IS receiving revenue.

Concretely:

1. **Add a folder** on `/folders` and set its default price (e.g. "shopify" → 2000 PKR). One-time setup.
2. **Open a student** on `/students/{id}` and click **Sell access**.
3. **Pick the folder** (price auto-fills from the folder's default — override per sale if needed).
4. **Set the fee status**:
   - `Pending` — student agreed but hasn't paid yet (default).
   - `Paid` — money already in.
   - `Waived` — free comp, no charge.
5. **Fill "Credited to"** with the wallet/bank name where the money should land.
6. Click **Sell & grant access** — both the Drive permission and the matching revenue event are created.
7. Later, when the payment hits, open **Sales & Revenue** (`/fees`) and click **Mark paid** on the row. The fee flips to paid AND the revenue event flips to received, in one click.

Dashboard tiles, the `/revenue` list, and the payouts engine all read from the same data. There's no separate "record a payment" path — you can't have revenue that isn't tied to a sale.

## How access grants work

When you click **Sell access** on a student and submit:

1. App calls `permissions.create` on the folder with `role=reader`, `emailAddress=<student's Google email>`, `expirationTime=<now + N days>`.
2. Student's Google account immediately receives a viewer-only permission on that folder.
3. We store the Drive permission ID locally so we can revoke it later.
4. If a price was set, a `RevenueEvent` is created in `pending` (or `received` if you marked it paid at sale time).
5. Background job (`expire_grants_job`) runs every 30 min; when `expires_at < now`, we revoke the Drive permission, mark the grant as `expired`, and cancel the linked revenue event.

Students consume the content on Google Drive itself — no custom viewer, no bandwidth cost. Google's `role=reader` plus `viewersCanCopyContent=false` is the strongest native restriction.

## Revenue & profit-sharing lifecycle

The model is unified — there's no separate "Record new revenue" page anymore. New revenue only comes from a fee on a grant.

1. **Sell** a grant with a price → revenue event in `pending`.
2. While status is `pending`, it's a **receivable**; dashboard & revenue page surface it.
3. **Mark paid** (on `/fees`) → status flips to `received` and `compute_distributions_for()` snapshots the per-user shares based on each active user's `default_ratio`. We store the *applied* ratio so future edits don't rewrite history.
4. **Build payouts** on `/payouts` → groups each member's unpaid distributions into one Payout row.
5. **Mark paid** (the payout one) → payout becomes historical.

If active ratios don't sum to 1.0, the system falls back to an equal split and logs a warning in the UI ("Total active ratio: 0.85").

## One-time Google setup

See **[GOOGLE_SETUP.md](./GOOGLE_SETUP.md)** — it walks the client through:

1. Creating a Google Cloud project
2. Enabling the Drive API
3. Creating a Service Account
4. Downloading the JSON key into `secrets/`
5. Sharing the main Drive folder with the SA email at **Editor** level (one-time, done in main Drive)
6. (No need to share each individual lecture folder — visibility inherits.)

## Deployment

Two ways to give this to a team member or client:

### A) One-click installer (recommended)

Hand them the project folder. They double-click `install.bat` (at the project root). It:

- Detects Python 3.11+. If missing, downloads the official Windows installer from python.org and runs it for them.
- Creates a project venv at `gdrive-platform\venv\`.
- Installs all dependencies.
- Creates a Desktop shortcut to `start.bat` (or `DriveManager.exe`), branded with `favicon.ico`.

After install, the user just double-clicks **Drive Manager** on their Desktop. The app starts the server in a console window and opens Chrome to `http://localhost:8000`.

Re-running `install.bat` is safe — each step is a no-op if already done.

### B) Standalone .exe launcher

The project ships `DriveManager.exe` (built with PyInstaller, ~8 MB). Drop it next to `gdrive-platform\` on any Windows PC and double-click. It does the same job as `start.bat` but doesn't need a `.bat` association. The .exe is branded with `favicon.ico` so it shows up correctly in the taskbar and Start menu.

To rebuild: `pyinstaller --noconfirm --clean DriveManager.spec` (output goes to `dist\DriveManager.exe`; copy it to the project root for the team).

### Direct run (no installer)

If you have Python 3.11+ installed and just want to try it:

```bash
cd gdrive-platform
pip install -r requirements.txt
python run.py
# open http://localhost:8000
```

## Backup & data

- All data is in `data/app.db`. To back up, copy that file (while the app is stopped, to avoid lock contention).
- The data file in `data/app.db.dev-backup` is a previous snapshot kept for safety.
- To migrate to PostgreSQL, set `DATABASE_URL=postgresql://…` in `.env`. Models are portable.

To wipe everything and start fresh: stop the app, delete `data/app.db`, restart. The first request re-creates the schema and seeds the owner.

## Security notes

- Default admin password is `admin123` — **change it on first login** (Team page → Reset password).
- `APP_SECRET` in `.env` must be a long random string — used to sign session JWTs.
- Run behind HTTPS (nginx, Caddy, Cloudflare Tunnel) for production. The cookie is `httponly` and `samesite=lax`.
- Drive permissions created by the app are view-only and time-bound; the background job revokes them on expiry.

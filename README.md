# Havenly

Single-owner rental management: React/TypeScript + FastAPI + SQLite. The frontend
now reads and writes the authenticated API. No sample records are inserted.
The original backend/rental_manager.db is preserved, not overwritten.

## Local setup

Python 3.13 and Node 22 are installed on the development laptop.

Terminal 1:

```sh
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py create-owner
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

If .venv does not exist, first run `python3 -m venv .venv`.
Create-owner prompts privately for a password of at least 12 characters. There
is no public sign-up route and no default password. Do not paste your password
into source code, chat, or environment examples.

Terminal 2:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies /api to the backend. Keep the same browser
hostname (localhost) throughout login. Restart both old development servers after
installing this update. It replaces the prototype backend and frontend.

1. Sign in using the owner credentials.
2. Properties → Add property → Units & details → add apartment/unit labels.
   For standalone commercial property, label its single space "Premises".
3. Add tenant contacts, then a lease linking one or more tenants to a unit.
4. Transactions → Add monthly entry. Choose a month, property, and optional unit.
5. Upload documents, then assign their property/tenant/lease/receipt links.
6. Dashboard and Reports read the saved monthly records. Select the month you entered.

Property, tenant and unit removal is archival so history is retained. Records
can be restored. Current/future leases prevent archiving related entities.
Lease dates are inclusive. To end tenancy, set its final occupied date; cancel
only a lease that should not take effect. Overlapping leases are rejected.
Deposits received/refunded/deducted are separate from profit.

## Database & migrations

SQLite is built into Python. No database server or Docker is required.
The default persistent folder is backend/data; override with an absolute
HAVENLY_DATA_DIR environment variable. SQLite database and private uploads live
together in that folder. Never put it inside frontend/public or frontend/dist.

Numbered SQL migrations in backend/migrations are applied transactionally on
startup and recorded in schema_migrations. Add a new numbered migration for
schema changes; never edit an already applied migration. Run backup first.
This project uses a small SQL migration runner rather than Alembic/SQLModel.

Schema:
- owners + sessions + login_attempts: one owner, hashed sessions, throttled login.
- properties → units → leases; lease_tenants connects roommates and tenancy history.
- tenants: contacts, emergency details, notes, archive state.
- categories: one rent category, five expenses; last two names customizable.
- monthly_records → six monthly_amounts; unique property/unit/month.
- deposit_transactions: receipts, refunds, deductions; refunds cannot exceed holdings.
- documents: private file metadata and foreign keys to property/unit/tenant/lease/record.

All money is integer cents, validated on the server. Use one currency per
portfolio; changing its label after leases or records exist is prohibited.
Property-wide records represent shared costs and must not duplicate unit records.
Both scopes are added together in reports. Rent means received rent; agreed rent
is on the lease. This does not generate charges, arrears or overdue balances.

Legacy import, only into an empty new property table:

```sh
cd backend
source .venv/bin/activate
python manage.py import-legacy rental_manager.db
```

Old in-memory prototype changes were not saved and cannot be recovered. Browser
localStorage profile names are not migrated into the new private account.

## Tests

```sh
cd backend
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest -v test_app
cd ../frontend
npm run build
npm run lint
```

Backend tests use temporary databases, never the owner's data. They cover login,
CSRF, session revocation, rate limits, lease overlap, foreign keys, cents validation,
duplicate monthly records, uploads/downloads, session restart and backup restore.
They also cover concurrent API reads/writes, competing deposit refunds, missing
uploads in backup manifests, and consistency of document links and parent edits.

Browser tests:

```sh
cd frontend
npx playwright install chromium
npm run test:e2e
```

On macOS 13, current Playwright Chromium is unsupported. If Google Chrome is
already installed, use `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` instead.

To test the built frontend with production security settings over local HTTPS:

```sh
npm run build
E2E_PRODUCTION=1 PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

See [the staging verification gate](deploy/STAGING.md) for actual proxy, service,
backup timer and restart checks required before public deployment.

Browser tests start a separate API on port 8011 with a temporary test database and
an explicitly test-only owner, and a Vite server on 5174. They do not use your
production account. See playwright.config.ts and backend/e2e_server.py.

On macOS 13, if current Playwright Chromium cannot be installed, use the installed
Google Chrome instead: `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e`.

## Backups and restoration

From backend with its virtual environment activated:

```sh
python manage.py backup /absolute/private/backups/havenly-2026-09-20
python manage.py restore /absolute/private/backups/havenly-2026-09-20 /absolute/private/restored-havenly
```

Backup destinations must be new directories. Backups use SQLite's online backup
API and copy every referenced immutable upload. The manifest checksums each file.
Restoration validates checksums, foreign keys and database integrity and refuses
to overwrite an existing destination. Stop the server, point HAVENLY_DATA_DIR to
the restored directory and restart. Restored sessions are revoked; sign in again.

Deleted documents are hidden and blocked from download; bytes and metadata are
retained for operator recovery and consistent backups. They are not permanently
erased. Backups include these files and sensitive owner/tenant records. Store
backups with restricted permissions and encrypted off-site copies. Select a
retention period and monitor storage use; no destructive automatic purge is installed.

## Hosting

Use one Linux service instance on a persistent disk, not an ephemeral/serverless
filesystem. Deploy examples are in deploy/. Hosting is not provisioned or activated
by this repository; choose a server/domain and configure DNS before launch.

1. Copy the app into /opt/havenly, install Python 3.13 + Node 22, create a dedicated
   unprivileged havenly service user, and grant it the data/backup folders only.
2. Build frontend with npm ci && npm run build. The backend serves frontend/dist
   and /api from the same origin; only the reverse proxy is internet-facing.
3. Create a venv under backend and install requirements.txt.
4. Set /etc/havenly.env (mode 600):
   HAVENLY_ENV=production
   HAVENLY_ORIGIN=https://your-real-domain
   HAVENLY_DATA_DIR=/var/lib/havenly
5. Create /var/lib/havenly and /var/backups/havenly owned by the service user,
   mode 700. Provision the owner using the same HAVENLY_DATA_DIR.
6. Adapt deploy/havenly.service and deploy/Caddyfile. Configure Caddy with your
   real domain and HTTPS, and expose only ports 80/443. The API binds loopback.
7. Install and enable the service and backup timer examples. Check their logs and
   monitor /api/health. Copy backups off-server; a local disk backup alone is
   insufficient for disk failure.
8. Test sign-in, create/edit records, refresh, restart service, download documents,
   sign-out, unauthenticated access rejection, and restore a backup in a separate
   directory before putting real tenant documents into the service.

Production sets Secure/HttpOnly/SameSite cookies, CSRF checks, origin checks,
security headers, no-store API responses, and disables public API documentation.
Sessions last 12 hours. Do not run with --reload in production.

Reset a forgotten password locally on the server:

```sh
python manage.py reset-password
```

Run with the same data directory as the service. This revokes existing sessions.
No email password-reset service or external integrations are required.

References: [FastAPI HTTPS deployment](https://fastapi.tiangolo.com/deployment/https/),
[SQLite online backups](https://www.sqlite.org/backup.html).

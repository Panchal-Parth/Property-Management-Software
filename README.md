# Havenly

Single-owner rental management: React/TypeScript + FastAPI + SQLite. The frontend
reads and writes an authenticated API. Normal startup never inserts sample records.
Private portfolio data and uploads remain on the server and are excluded from Git.

## Local setup

Install Python 3.13 and Node.js 22 (including npm). SQLite ships with Python;
no separate database server is needed.

Terminal 1:

```sh
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

If .venv does not exist, first run `python3 -m venv .venv`.
To sign up through the website, configure Brevo email delivery as described below.
The first verified signup creates the single owner. If email is not configured,
`python manage.py create-owner` remains available as a local setup option; it
prompts privately for a password of at least 12 characters. There is no default
password. Do not paste your password into source code or chat.

## Email verification and recovery

Create a Brevo account, verify your sender email/domain, and create an API key
for this application. Set `BREVO_API_KEY` and
`HAVENLY_MAIL_FROM` in the **backend server environment** before starting it.
The sender must be approved in Brevo. A `.env` file is ignored by Git, but the
app does not load it automatically: export these values in the terminal or your
service environment. Never place the API key in frontend code.

When the owner account is empty, the sign-in page offers verified email signup.
For an existing owner, Forgot password sends a code to the attached address.
Settings offers code-protected password changes and email changes; an email
change requires codes from both the old and new inboxes. Codes expire in 10
minutes, have limited attempts, and are throttled. Successful credential
changes revoke previous sessions. The server management reset command remains
an emergency option if access to the email account is lost.

Terminal 2:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies /api to the backend. Use the same browser
hostname throughout login (`localhost` and `127.0.0.1` have separate browser storage).
If your API uses a different port, set `HAVENLY_API_TARGET` when starting Vite.
After pulling new backend migrations, restart the API so they are applied.

1. Sign in using the owner credentials.
2. Properties → Add property → Units & details → add apartment/unit labels.
   For standalone commercial property, label its single space "Premises".
3. Add tenant contacts, then a lease linking one or more tenants to a unit.
4. Transactions → Add monthly entry. Choose a month, property, and optional unit.
5. Upload documents, then assign their property/tenant/lease/receipt links.
6. Dashboard and Transactions offer month or year-to-date views; Reports can filter
   all time, a specific month, or a specific year before export.

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
- notification_dismissals: cleared vacancy and expiring-lease notices for the owner.

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
Notification dismissals are stored in SQLite and persist across sign-in and devices.

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
uploads in backup manifests, consistency of document links and parent edits, and
notification dismissal across logout and sign-in.

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
   mode 700. Add `BREVO_API_KEY` and `HAVENLY_MAIL_FROM` to the private service
   environment, then sign up on the website or provision the owner locally using
   the same HAVENLY_DATA_DIR.
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
Email recovery requires a configured Brevo sender and API key. The local reset
command is an emergency fallback if the mailbox or provider is unavailable.

## Private rent records and demo workspace

Monthly entries record **rent actually received**. Optional expected rent is a
comparison only, not income or a total arrears balance. Payment notes support
multiple lines and appear in expandable panels in Transactions, recent dashboard
entries, and property financial history. Notes are searchable in Transactions.
Unit contacts and rent on file do not establish a legal lease; enter confirmed
lease dates separately. Workbook imports retain source rows in the private database
for review. Keep databases, uploads, spreadsheets and backups out of Git.

To try fictional leases and full/partial/unpaid examples without changing your real
portfolio, build the frontend and launch the isolated demo from the project root:

```sh
cd frontend
npm run build
cd ..
backend/.venv/bin/python backend/demo_server.py
```

Open `http://127.0.0.1:8012`. Use `demo@example.test` and the temporary password
printed in that terminal. The demo uses a separate temporary database, binds only
to localhost, and deletes its fictional records when stopped with Ctrl+C. It is
not a deployment mode. The real database is never read or copied into the demo.

## Repository privacy

Commit source code and documentation only. `.gitignore` excludes `backend/data/`,
`backups/`, SQLite databases, uploads, local environment files, built assets, and
browser test output. Do not add real rent spreadsheets, tenant documents, API keys,
or database exports. Before publishing, check `git status --short` and
`git diff --cached --name-only`. A backup or database in Git history remains
sensitive even if deleted in a later commit.

References: [FastAPI HTTPS deployment](https://fastapi.tiangolo.com/deployment/https/),
[SQLite online backups](https://www.sqlite.org/backup.html).

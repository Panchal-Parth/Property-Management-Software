import json
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from db import BASE, UPLOADS, connect, migrate, rows
from schemas import DocumentIn, DepositIn, LeaseIn, Login, MonthlyIn, PropertyIn, SettingsIn, TenantIn, UnitIn
from schemas import CodeConfirm, EmailChange, EmailRequest, NotificationDismissIn, PasswordChange, PasswordReset, SignupRequest
import email_delivery
from security import password_hash, token_hash, verify_password

PRODUCTION = os.getenv("HAVENLY_ENV") == "production"
ORIGIN = os.getenv("HAVENLY_ORIGIN", "http://localhost:5173").rstrip("/")
COOKIE = "havenly_session"
MAX_UPLOAD = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(app):
    if PRODUCTION and not ORIGIN.startswith("https://"):
        raise RuntimeError("Production requires HAVENLY_ORIGIN=https://your-domain")
    migrate()
    yield


app = FastAPI(title="Havenly", lifespan=lifespan, docs_url=None if PRODUCTION else "/docs",
              redoc_url=None, openapi_url=None if PRODUCTION else "/openapi.json")


@app.middleware("http")
async def headers(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        allowed = {ORIGIN} if PRODUCTION else {ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
        if origin and origin not in allowed:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_UPLOAD + 1024 * 1024):
            return JSONResponse({"detail": "Request too large (15 MB maximum file)"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    if PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(request, exc):
    message = str(exc)
    if "overlap" in message:
        detail = "Lease dates overlap another lease for this unit."
    elif "monthly_scope" in message:
        detail = "A monthly entry already exists for this property/unit and month."
    else:
        detail = "This record conflicts with existing data. Check duplicate names and linked records."
    return JSONResponse({"detail": detail}, status_code=409)


def database(request: Request):
    c = connect()
    try:
        with c:
            # One read snapshot, or a reserved writer lock covering validation
            # and mutation. Prevents archive/lease and deposit races.
            c.execute("BEGIN" if request.method in ("GET", "HEAD", "OPTIONS") else "BEGIN IMMEDIATE")
            yield c
    finally:
        c.close()


def require_owner(request: Request, c=Depends(database)):
    token = request.cookies.get(COOKIE, "")
    session = c.execute("SELECT * FROM sessions WHERE token_hash=? AND expires>?", (token_hash(token), int(time.time()))).fetchone()
    if not session:
        raise HTTPException(401, "Sign in to continue.")
    if request.method not in ("GET", "HEAD") and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"]):
        raise HTTPException(403, "Session verification failed. Refresh and try again.")
    return dict(session)


def exists(c, table, id, active=False):
    row = c.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
    if not row or (active and row["archived"]):
        raise HTTPException(404, f"{table.title()} record not available")
    return dict(row)


def today(c):
    owner = c.execute("SELECT timezone FROM owners WHERE id=1").fetchone()
    return datetime.now(ZoneInfo(owner["timezone"] if owner else "UTC")).date().isoformat()


def write(c, table, values, id=None):
    # table and field names originate only in server models/routes.
    if id is None:
        keys = list(values)
        return c.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", tuple(values.values())).lastrowid
    exists(c, table, id)
    c.execute(f"UPDATE {table} SET " + ",".join(f"{k}=?" for k in values) + ",updated_at=CURRENT_TIMESTAMP WHERE id=?", (*values.values(), id))
    return id


@app.get("/api/health")
def health(c=Depends(database)):
    c.execute("SELECT 1")
    return {"status": "healthy"}


@app.get("/api/auth/status")
def auth_status(c=Depends(database)):
    return {"configured": bool(c.execute("SELECT 1 FROM owners").fetchone()), "email_ready": email_delivery.configured()}


def issue_code(c, request, purpose, destination, payload=''):
    now = int(time.time())
    address = request.client.host if request.client else 'unknown'
    c.execute('DELETE FROM email_send_attempts WHERE attempted_at<?', (now - 3600,))
    if c.execute('SELECT count(*) FROM email_send_attempts WHERE address=?', (address,)).fetchone()[0] >= 12:
        raise HTTPException(429, 'Too many email requests. Try again in an hour.')
    previous = c.execute('SELECT sent_at FROM email_challenges WHERE purpose=? AND destination=?', (purpose,destination)).fetchone()
    if previous and now - previous['sent_at'] < 60:
        raise HTTPException(429, 'Wait one minute before requesting another code.')
    code = f'{secrets.randbelow(1_000_000):06d}'
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + code).encode()).hexdigest()
    try:
        email_delivery.send_code(destination, code, purpose)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    c.execute('INSERT INTO email_send_attempts VALUES (?,?)', (address, now))
    c.execute('INSERT OR REPLACE INTO email_challenges(purpose,destination,code_hash,salt,payload,expires_at,sent_at,attempts) VALUES(?,?,?,?,?,?,?,0)',
              (purpose,destination,digest,salt,payload,now+600,now))


def consume_code(c, purpose, destination, code):
    row = c.execute('SELECT * FROM email_challenges WHERE purpose=? AND destination=?', (purpose,destination)).fetchone()
    if not row or row['expires_at'] < int(time.time()) or row['attempts'] >= 5:
        raise HTTPException(400, 'Code expired or unavailable. Request a new code.')
    c.execute('UPDATE email_challenges SET attempts=attempts+1 WHERE purpose=? AND destination=?', (purpose,destination))
    c.commit()  # Preserve attempts even when a code is wrong.
    actual = hashlib.sha256((row['salt'] + code).encode()).hexdigest()
    if not hmac.compare_digest(row['code_hash'], actual):
        raise HTTPException(400, 'Code incorrect. Try again or request a new one.')
    return row['payload']


@app.post('/api/auth/signup/request')
def signup_request(body: SignupRequest, request: Request, c=Depends(database)):
    if c.execute('SELECT 1 FROM owners').fetchone():
        raise HTTPException(409, 'This single-owner workspace is already set up. Sign in or reset the password.')
    issue_code(c, request, 'signup', body.email, json.dumps({'name':body.name,'password_hash':password_hash(body.password)}))
    return {'ok': True}


@app.post('/api/auth/signup/confirm')
def signup_confirm(body: CodeConfirm, c=Depends(database)):
    if c.execute('SELECT 1 FROM owners').fetchone():
        raise HTTPException(409, 'This workspace is already set up.')
    payload = json.loads(consume_code(c,'signup',body.email,body.code))
    c.execute('INSERT INTO owners(id,email,name,password_hash) VALUES(1,?,?,?)', (body.email,payload['name'],payload['password_hash']))
    c.execute('DELETE FROM email_challenges')
    return {'ok': True}


@app.post('/api/auth/reset/request')
def reset_request(body: EmailRequest, request: Request, c=Depends(database)):
    owner = c.execute('SELECT email FROM owners WHERE id=1').fetchone()
    if owner and hmac.compare_digest(owner['email'].lower(),body.email):
        issue_code(c, request, 'reset', body.email)
    return {'ok': True, 'message': 'If this email is attached to the account, a code has been sent.'}


@app.post('/api/auth/reset/confirm')
def reset_confirm(body: PasswordReset, c=Depends(database)):
    owner = c.execute('SELECT email FROM owners WHERE id=1').fetchone()
    if not owner or not hmac.compare_digest(owner['email'].lower(),body.email):
        raise HTTPException(400, 'Code expired or unavailable. Request a new code.')
    consume_code(c,'reset',body.email,body.code)
    c.execute('UPDATE owners SET password_hash=? WHERE id=1',(password_hash(body.password),))
    c.execute('DELETE FROM sessions')
    c.execute('DELETE FROM email_challenges')
    return {'ok': True}


@app.post('/api/auth/change-password/request')
def change_password_request(request: Request, owner=Depends(require_owner), c=Depends(database)):
    email = c.execute('SELECT email FROM owners WHERE id=1').fetchone()[0]
    issue_code(c, request, 'change_password', email)
    return {'ok': True}


@app.post('/api/auth/change-password/confirm')
def change_password_confirm(body: PasswordChange, owner=Depends(require_owner), c=Depends(database)):
    email = c.execute('SELECT email FROM owners WHERE id=1').fetchone()[0]
    consume_code(c,'change_password',email,body.code)
    c.execute('UPDATE owners SET password_hash=? WHERE id=1',(password_hash(body.password),))
    c.execute('DELETE FROM sessions')
    c.execute('DELETE FROM email_challenges')
    return {'ok': True}


@app.post('/api/auth/change-email/request')
def change_email_request(body: EmailRequest, request: Request, owner=Depends(require_owner), c=Depends(database)):
    current = c.execute('SELECT email FROM owners WHERE id=1').fetchone()[0]
    if hmac.compare_digest(current.lower(),body.email):
        raise HTTPException(422, 'Choose a different email address.')
    issue_code(c, request, 'change_email_old', current, body.email)
    issue_code(c, request, 'change_email_new', body.email, current)
    return {'ok': True}


@app.post('/api/auth/change-email/confirm')
def change_email_confirm(body: EmailChange, owner=Depends(require_owner), c=Depends(database)):
    current = c.execute('SELECT email FROM owners WHERE id=1').fetchone()[0]
    old_target = c.execute('SELECT payload FROM email_challenges WHERE purpose=? AND destination=?', ('change_email_old',current)).fetchone()
    if not old_target or old_target['payload'] != body.email:
        raise HTTPException(400, 'Email change request expired. Request new codes.')
    consume_code(c,'change_email_old',current,body.current_code)
    previous = consume_code(c,'change_email_new',body.email,body.new_code)
    if previous != current:
        raise HTTPException(400, 'Email change request expired. Request new codes.')
    c.execute('UPDATE owners SET email=? WHERE id=1',(body.email,))
    c.execute('DELETE FROM sessions')
    c.execute('DELETE FROM email_challenges')
    return {'ok': True}


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response, c=Depends(database)):
    now = int(time.time())
    address = request.client.host if request.client else "unknown"
    c.execute("DELETE FROM login_attempts WHERE attempted_at<?", (now - 900,))
    count = c.execute("SELECT count(*) FROM login_attempts WHERE address=?", (address,)).fetchone()[0]
    if count >= 10:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    c.execute("INSERT INTO login_attempts VALUES (?,?)", (address, now))
    c.commit()  # failed authentication must also retain its rate-limit attempt
    owner = c.execute("SELECT * FROM owners WHERE id=1").fetchone()
    encoded = owner["password_hash"] if owner else password_hash("unconfigured-account")
    valid = verify_password(body.password, encoded)
    if not owner or owner["email"].casefold() != body.email.strip().casefold() or not valid:
        raise HTTPException(401, "Email or password is incorrect.")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    c.execute("DELETE FROM sessions WHERE expires<=?", (now,))
    c.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token_hash(token), 1, csrf, now + 43200))
    c.execute("DELETE FROM login_attempts WHERE address=?", (address,))
    response.set_cookie(COOKIE, token, httponly=True, secure=PRODUCTION, samesite="strict", max_age=43200, path="/")
    return {"csrf": csrf}


@app.get("/api/auth/session")
def session(owner=Depends(require_owner)):
    return {"csrf": owner["csrf"]}


@app.post("/api/auth/logout")
def logout(response: Response, owner=Depends(require_owner), c=Depends(database)):
    c.execute("DELETE FROM sessions WHERE token_hash=?", (owner["token_hash"],))
    response.delete_cookie(COOKIE, path="/", secure=PRODUCTION, httponly=True, samesite="strict")
    return {"ok": True}


@app.get("/api/state")
def state(owner=Depends(require_owner), c=Depends(database)):
    settings = dict(c.execute("SELECT name,email,currency,timezone FROM owners WHERE id=1").fetchone())
    leases = rows(c, "SELECT * FROM leases ORDER BY start_date DESC")
    for lease in leases:
        lease["tenant_ids"] = [r[0] for r in c.execute("SELECT tenant_id FROM lease_tenants WHERE lease_id=?", (lease["id"],))]
    records = rows(c, "SELECT * FROM monthly_records ORDER BY month DESC,id DESC")
    for record in records:
        record["amounts"] = [r[0] for r in c.execute("SELECT amount_cents FROM monthly_amounts WHERE record_id=? ORDER BY category_id", (record["id"],))]
    return {"settings": settings, "today": today(c), "categories": rows(c, "SELECT * FROM categories ORDER BY id"),
            "properties": rows(c, "SELECT * FROM properties ORDER BY id DESC"),
            "units": rows(c, "SELECT * FROM units ORDER BY property_id,label"),
            "tenants": rows(c, "SELECT * FROM tenants ORDER BY name"), "leases": leases, "records": records,
            "documents": rows(c, "SELECT id,filename,mime,size,kind,notes,property_id,unit_id,tenant_id,lease_id,record_id,created_at FROM documents WHERE deleted=0 ORDER BY id DESC"),
            "deposits": rows(c, "SELECT * FROM deposit_transactions ORDER BY date DESC,id DESC"),
            "dismissed_notifications": [row[0] for row in c.execute("SELECT notification_id FROM notification_dismissals WHERE owner_id=?", (owner["owner_id"],))]}


@app.post("/api/notifications/dismiss")
def dismiss_notifications(body: NotificationDismissIn, owner=Depends(require_owner), c=Depends(database)):
    c.executemany("INSERT OR IGNORE INTO notification_dismissals(owner_id,notification_id) VALUES (?,?)",
                  ((owner["owner_id"], notification_id) for notification_id in body.ids))
    return {"dismissed": body.ids}


@app.put("/api/settings")
def settings(body: SettingsIn, owner=Depends(require_owner), c=Depends(database)):
    names = ["Rent", "Water", "Repairs", "Miscellaneous", body.category5, body.category6]
    if len({n.casefold() for n in names}) != 6:
        raise HTTPException(422, "Category names must be distinct.")
    previous = c.execute("SELECT currency FROM owners WHERE id=1").fetchone()[0]
    if previous != body.currency and (c.execute("SELECT 1 FROM monthly_records LIMIT 1").fetchone() or c.execute("SELECT 1 FROM leases LIMIT 1").fetchone()):
        raise HTTPException(409, "Currency cannot change after recording leases or finances. No currency conversion is performed.")
    c.execute("UPDATE owners SET name=?,currency=?,timezone=? WHERE id=1", (body.name, body.currency, body.timezone))
    c.execute("UPDATE categories SET name=? WHERE id=5", ("__temporary_" + secrets.token_hex(16),))
    c.execute("UPDATE categories SET name=? WHERE id=6", (body.category6,))
    c.execute("UPDATE categories SET name=? WHERE id=5", (body.category5,))
    return {"ok": True}


@app.post("/api/properties")
@app.put("/api/properties/{id}")
def property_save(body: PropertyIn, id: int | None = None, owner=Depends(require_owner), c=Depends(database)):
    return {"id": write(c, "properties", body.model_dump(), id)}


@app.post("/api/units")
@app.put("/api/units/{id}")
def unit_save(body: UnitIn, id: int | None = None, owner=Depends(require_owner), c=Depends(database)):
    exists(c, "properties", body.property_id, active=True)
    if body.tenant_id is not None:
        exists(c, "tenants", body.tenant_id, active=True)
    if id:
        current = exists(c, "units", id)
        if current["property_id"] != body.property_id:
            raise HTTPException(409, "Units cannot move between properties; create a new unit instead.")
    if body.unavailable and id and c.execute("SELECT 1 FROM leases WHERE unit_id=? AND cancelled=0 AND end_date>=?", (id, today(c))).fetchone():
        raise HTTPException(409, "End or cancel current/future leases before marking this unit unavailable.")
    return {"id": write(c, "units", body.model_dump(), id)}


@app.post("/api/tenants")
@app.put("/api/tenants/{id}")
def tenant_save(body: TenantIn, id: int | None = None, owner=Depends(require_owner), c=Depends(database)):
    return {"id": write(c, "tenants", body.model_dump(), id)}


@app.post("/api/{resource}/{id}/archive")
def archive(resource: str, id: int, owner=Depends(require_owner), c=Depends(database)):
    if resource not in ("properties", "units", "tenants"):
        raise HTTPException(404)
    exists(c, resource, id)
    d = today(c)
    if resource == "properties":
        blocked = c.execute("SELECT 1 FROM leases l JOIN units u ON u.id=l.unit_id WHERE u.property_id=? AND l.cancelled=0 AND l.end_date>=?", (id, d)).fetchone()
    elif resource == "units":
        blocked = c.execute("SELECT 1 FROM leases WHERE unit_id=? AND cancelled=0 AND end_date>=?", (id, d)).fetchone()
    else:
        blocked = c.execute("SELECT 1 FROM lease_tenants t JOIN leases l ON l.id=t.lease_id WHERE t.tenant_id=? AND l.cancelled=0 AND l.end_date>=?", (id, d)).fetchone()
    if blocked:
        raise HTTPException(409, "End or cancel current/future leases before archiving.")
    c.execute(f"UPDATE {resource} SET archived=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
    return {"ok": True}


@app.post("/api/{resource}/{id}/restore")
def unarchive(resource: str, id: int, owner=Depends(require_owner), c=Depends(database)):
    if resource not in ("properties", "units", "tenants"):
        raise HTTPException(404)
    exists(c, resource, id)
    c.execute(f"UPDATE {resource} SET archived=0,updated_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
    return {"ok": True}


@app.post("/api/leases")
@app.put("/api/leases/{id}")
def lease_save(body: LeaseIn, id: int | None = None, owner=Depends(require_owner), c=Depends(database)):
    unit = exists(c, "units", body.unit_id, active=True)
    exists(c, "properties", unit["property_id"], active=True)
    if unit["unavailable"] and not body.cancelled:
        raise HTTPException(409, "This unit is unavailable for rental.")
    for tenant_id in body.tenant_ids:
        exists(c, "tenants", tenant_id, active=True)
    values = body.model_dump(mode="json", exclude={"tenant_ids"})
    lease_id = write(c, "leases", values, id)
    c.execute("DELETE FROM lease_tenants WHERE lease_id=?", (lease_id,))
    c.executemany("INSERT INTO lease_tenants VALUES (?,?)", [(lease_id, tid) for tid in body.tenant_ids])
    validate_linked_documents(c, "lease_id", lease_id)
    return {"id": lease_id}


@app.post("/api/records")
@app.put("/api/records/{id}")
def record_save(body: MonthlyIn, id: int | None = None, owner=Depends(require_owner), c=Depends(database)):
    exists(c, "properties", body.property_id, active=True)
    if body.unit_id:
        unit = exists(c, "units", body.unit_id, active=True)
        if unit["property_id"] != body.property_id:
            raise HTTPException(422, "Choose a unit belonging to this property.")
    record_id = write(c, "monthly_records", body.model_dump(exclude={"amounts"}), id)
    c.execute("DELETE FROM monthly_amounts WHERE record_id=?", (record_id,))
    c.executemany("INSERT INTO monthly_amounts VALUES (?,?,?)", [(record_id, i + 1, amount) for i, amount in enumerate(body.amounts)])
    validate_linked_documents(c, "record_id", record_id)
    return {"id": record_id}


@app.delete("/api/records/{id}")
def record_delete(id: int, owner=Depends(require_owner), c=Depends(database)):
    exists(c, "monthly_records", id)
    c.execute("DELETE FROM monthly_records WHERE id=?", (id,))
    return {"ok": True}


@app.post("/api/deposits")
def deposit_save(body: DepositIn, owner=Depends(require_owner), c=Depends(database)):
    exists(c, "leases", body.lease_id)
    balance = c.execute("SELECT coalesce(sum(CASE WHEN kind='received' THEN amount_cents ELSE -amount_cents END),0) FROM deposit_transactions WHERE lease_id=?", (body.lease_id,)).fetchone()[0]
    if body.kind != "received" and body.amount_cents > balance:
        raise HTTPException(409, "Refund or deduction exceeds the deposit held.")
    return {"id": write(c, "deposit_transactions", body.model_dump(mode="json"))}


def validate_document(c, body):
    property_ids, unit_ids = set(), set()
    for field, table in (("property_id", "properties"), ("unit_id", "units"), ("tenant_id", "tenants"), ("lease_id", "leases"), ("record_id", "monthly_records")):
        value = getattr(body, field)
        if value:
            exists(c, table, value)
    if body.property_id:
        property_ids.add(body.property_id)
    if body.unit_id:
        unit_ids.add(body.unit_id)
        property_ids.add(exists(c, "units", body.unit_id)["property_id"])
    if body.lease_id:
        lease = exists(c, "leases", body.lease_id)
        unit = exists(c, "units", lease["unit_id"])
        property_ids.add(unit["property_id"])
        unit_ids.add(unit["id"])
        if body.tenant_id and not c.execute("SELECT 1 FROM lease_tenants WHERE lease_id=? AND tenant_id=?", (body.lease_id, body.tenant_id)).fetchone():
            raise HTTPException(422, "Document tenant is not on the linked lease.")
    if body.record_id:
        record = exists(c, "monthly_records", body.record_id)
        property_ids.add(record["property_id"])
        if record["unit_id"]:
            unit_ids.add(record["unit_id"])
    if len(property_ids) > 1 or len(unit_ids) > 1:
        raise HTTPException(422, "All document links must refer to the same property and unit.")


def validate_linked_documents(c, field, id):
    # field is a server-owned constant. Parent edits must not invalidate links.
    for row in c.execute(f"SELECT * FROM documents WHERE {field}=? AND deleted=0", (id,)):
        body = DocumentIn(**{name: row[name] for name in DocumentIn.model_fields})
        validate_document(c, body)


@app.post("/api/documents")
def upload(file: UploadFile = File(...), owner=Depends(require_owner), c=Depends(database)):
    name = Path((file.filename or "document").replace("\\", "/")).name[:180]
    suffix = Path(name).suffix.lower()
    mime = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix)
    if not mime:
        raise HTTPException(422, "Upload a PDF, PNG or JPEG document.")
    storage = secrets.token_hex(24) + suffix
    path = UPLOADS / storage
    size = 0
    try:
        with path.open("xb") as target:
            path.chmod(0o600)
            while chunk := file.file.read(1024 * 1024):
                if size == 0:
                    valid = (mime == "application/pdf" and chunk.startswith(b"%PDF-")) or (mime == "image/png" and chunk.startswith(b"\x89PNG\r\n\x1a\n")) or (mime == "image/jpeg" and chunk.startswith(b"\xff\xd8\xff"))
                    if not valid:
                        raise HTTPException(422, "File contents do not match its extension.")
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "File exceeds 15 MB.")
                target.write(chunk)
        if not size:
            raise HTTPException(422, "Empty files cannot be uploaded.")
        id = write(c, "documents", {"filename": name, "storage_name": storage, "mime": mime, "size": size, "kind": "Other"})
        c.commit()
        return {"id": id}
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.put("/api/documents/{id}")
def document_update(id: int, body: DocumentIn, owner=Depends(require_owner), c=Depends(database)):
    document = exists(c, "documents", id)
    if document["deleted"]:
        raise HTTPException(404)
    validate_document(c, body)
    if "/" in body.filename or "\\" in body.filename or any(ord(ch) < 32 for ch in body.filename):
        raise HTTPException(422, "Use a filename without path separators or control characters.")
    return {"id": write(c, "documents", body.model_dump(), id)}


@app.get("/api/documents/{id}/download")
def download(id: int, owner=Depends(require_owner), c=Depends(database)):
    doc = exists(c, "documents", id)
    path = UPLOADS / doc["storage_name"]
    if doc["deleted"] or not path.is_file():
        raise HTTPException(404, "Document not available.")
    return FileResponse(path, media_type="application/octet-stream", filename=doc["filename"], content_disposition_type="attachment")


@app.delete("/api/documents/{id}")
def document_delete(id: int, owner=Depends(require_owner), c=Depends(database)):
    exists(c, "documents", id)
    # Retain immutable bytes for consistent backups and operator recovery.
    c.execute("UPDATE documents SET deleted=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
    return {"ok": True}


@app.get("/api/{path:path}")
def missing_api(path: str):
    raise HTTPException(404, "API endpoint not found")


DIST = BASE.parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")

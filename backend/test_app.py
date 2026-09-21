import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HAVENLY_DATA_DIR"] = str(Path(self.tmp.name) / "data")
        os.environ.pop("HAVENLY_ENV", None)
        import db, main, manage
        self.db = importlib.reload(db)
        self.main = importlib.reload(main)
        self.manage = importlib.reload(manage)
        self.client = TestClient(self.main.app)
        self.client.__enter__()
        from security import password_hash
        with self.db.connect() as c:
            c.execute("INSERT INTO owners(id,email,name,password_hash) VALUES(1,?,?,?)",
                      ("owner@example.test", "Test Owner", password_hash("long-test-password")))
        self.login()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def login(self):
        r = self.client.post("/api/auth/login", json={"email": "owner@example.test", "password": "long-test-password"})
        self.assertEqual(r.status_code, 200, r.text)
        self.client.headers["x-csrf-token"] = r.json()["csrf"]

    def post(self, path, data, code=200):
        r = self.client.post("/api/" + path, json=data)
        self.assertEqual(r.status_code, code, r.text)
        return r.json()

    def setup_portfolio(self):
        p = self.post("properties", {"name": "Oak", "address": "12 Oak Street", "kind": "Apartment"})["id"]
        u = self.post("units", {"property_id": p, "label": "101", "floor": "1"})["id"]
        t = self.post("tenants", {"name": "Alex", "phone": "555-1234"})["id"]
        return p, u, t

    def test_auth_csrf_logout_and_rate_limit(self):
        cookie = self.client.cookies.get("havenly_session")
        with TestClient(self.main.app) as other:
            self.assertEqual(other.get("/api/state").status_code, 401)
            self.assertEqual(other.get("/api/documents/1/download").status_code, 401)
            other.cookies.set("havenly_session", cookie)
            self.assertEqual(other.post("/api/properties", json={"name": "x", "address": "y", "kind": "Apartment"}).status_code, 403)
        r = self.client.post("/api/auth/logout")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/state").status_code, 401)
        for _ in range(10):
            self.assertEqual(self.client.post("/api/auth/login", json={"email": "owner@example.test", "password": "bad"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "owner@example.test", "password": "bad"}).status_code, 429)

    def test_notification_dismissal_survives_logout_and_is_protected(self):
        notification_id = 'unit-12-after-0'
        self.assertEqual(self.client.post('/api/notifications/dismiss', json={'ids': [notification_id]}).status_code, 200)
        self.assertIn(notification_id, self.client.get('/api/state').json()['dismissed_notifications'])
        self.assertEqual(self.client.post('/api/notifications/dismiss', json={'ids': ['invalid']}).status_code, 422)
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/state').status_code, 401)
        self.assertEqual(self.client.post('/api/notifications/dismiss', json={'ids': [notification_id]}).status_code, 401)
        self.login()
        self.assertIn(notification_id, self.client.get('/api/state').json()['dismissed_notifications'])

    def test_offsite_backup_requires_remote_repository_and_cleans_snapshot(self):
        import offsite_backup
        password = Path(self.tmp.name) / 'restic-password'
        password.write_text('fictional-test-password')
        with patch.dict(os.environ, {'RESTIC_REPOSITORY': str(Path(self.tmp.name) / 'local'), 'RESTIC_PASSWORD_FILE': str(password)}):
            with self.assertRaisesRegex(RuntimeError, 'off-site'):
                offsite_backup.run_backup()
        calls = []
        with patch.dict(os.environ, {'RESTIC_REPOSITORY': 's3:https://example.invalid/bucket', 'RESTIC_PASSWORD_FILE': str(password)}), \
             patch.object(offsite_backup.shutil, 'which', return_value='/usr/bin/restic'), \
             patch.object(offsite_backup.subprocess, 'run', side_effect=lambda args, **kwargs: calls.append(args)):
            offsite_backup.run_backup()
        self.assertEqual([args[1] for args in calls], ['backup', 'check', 'forget'])
        self.assertFalse(Path(calls[0][-1]).exists())

    def test_email_signup_single_owner_and_otp_limits(self):
        with self.db.connect() as c:
            c.execute('DELETE FROM sessions')
            c.execute('DELETE FROM owners')
        sent = []
        with patch.object(self.main.email_delivery, 'send_code', side_effect=lambda to, code, purpose: sent.append((to, code, purpose))):
            payload = {'name': 'New Owner', 'email': 'new@example.test', 'password': 'a-very-long-new-password'}
            self.assertEqual(self.client.post('/api/auth/signup/request', json=payload).status_code, 200)
            self.assertEqual(sent[-1][2], 'signup')
            code = sent[-1][1]
            self.assertEqual(self.client.post('/api/auth/signup/confirm', json={'email': payload['email'], 'code': '000000' if code != '000000' else '111111'}).status_code, 400)
            self.assertEqual(self.client.post('/api/auth/signup/confirm', json={'email': payload['email'], 'code': code}).status_code, 200)
            self.assertEqual(self.client.post('/api/auth/signup/request', json=payload).status_code, 409)
            self.assertEqual(self.client.post('/api/auth/login', json={'email':payload['email'],'password':payload['password']}).status_code, 200)
        with self.db.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM owners').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM email_challenges').fetchone()[0],0)

    def test_email_recovery_and_change_require_codes(self):
        sent = []
        with patch.object(self.main.email_delivery, 'send_code', side_effect=lambda to, code, purpose: sent.append((to, code, purpose))):
            self.assertEqual(self.client.post('/api/auth/reset/request', json={'email':'other@example.test'}).status_code, 200)
            self.assertFalse(sent)
            self.assertEqual(self.client.post('/api/auth/reset/request', json={'email':'owner@example.test'}).status_code, 200)
            code = sent[-1][1]
            self.assertEqual(self.client.post('/api/auth/reset/confirm', json={'email':'owner@example.test','code':code,'password':'another-long-password'}).status_code, 200)
            self.assertEqual(self.client.get('/api/state').status_code, 401)
            fresh = self.client.post('/api/auth/login', json={'email':'owner@example.test','password':'another-long-password'})
            self.assertEqual(fresh.status_code,200)
            self.client.headers['x-csrf-token'] = fresh.json()['csrf']
            self.assertEqual(self.client.post('/api/auth/change-email/request', json={'email':'new@example.test'}).status_code,200)
            codes = {purpose: value for _, value, purpose in sent}
            self.assertEqual(self.client.post('/api/auth/change-email/confirm', json={'email':'new@example.test','current_code':codes['change_email_old'],'new_code':'000000' if codes['change_email_new'] != '000000' else '111111'}).status_code,400)
            self.assertEqual(self.client.post('/api/auth/change-email/confirm', json={'email':'new@example.test','current_code':codes['change_email_old'],'new_code':codes['change_email_new']}).status_code,200)
            self.assertEqual(self.client.get('/api/state').status_code,401)
            self.assertEqual(self.client.post('/api/auth/login',json={'email':'owner@example.test','password':'another-long-password'}).status_code,401)
            self.assertEqual(self.client.post('/api/auth/login',json={'email':'new@example.test','password':'another-long-password'}).status_code,200)

    def test_email_code_lockout_and_expiry(self):
        sent = []
        with patch.object(self.main.email_delivery, 'send_code', side_effect=lambda to, code, purpose: sent.append(code)):
            self.assertEqual(self.client.post('/api/auth/reset/request',json={'email':'owner@example.test'}).status_code,200)
            wrong = '000000' if sent[-1] != '000000' else '111111'
            for _ in range(5):
                self.assertEqual(self.client.post('/api/auth/reset/confirm',json={'email':'owner@example.test','code':wrong,'password':'another-long-password'}).status_code,400)
            self.assertEqual(self.client.post('/api/auth/reset/confirm',json={'email':'owner@example.test','code':sent[-1],'password':'another-long-password'}).status_code,400)
            with self.db.connect() as c:
                c.execute("UPDATE email_challenges SET expires_at=0 WHERE purpose='reset'")
            self.assertEqual(self.client.post('/api/auth/reset/confirm',json={'email':'owner@example.test','code':sent[-1],'password':'another-long-password'}).status_code,400)
            self.assertEqual(self.client.post('/api/auth/login',json={'email':'owner@example.test','password':'long-test-password'}).status_code,200)

    def test_lease_overlap_vacancy_archive_and_deposit(self):
        p, u, t = self.setup_portfolio()
        lease = {"unit_id": u, "tenant_ids": [t], "start_date": "2020-01-01", "end_date": "2099-12-31", "rent_cents": 125050, "deposit_cents": 200000}
        lid = self.post("leases", lease)["id"]
        self.post("leases", lease, 409)
        self.post("units/" + str(u) + "/archive", {}, 409)
        self.post("properties/" + str(p) + "/archive", {}, 409)
        self.post("tenants/" + str(t) + "/archive", {}, 409)
        self.post("deposits", {"lease_id": lid, "kind": "received", "amount_cents": 200000, "date": "2026-01-01"})
        self.post("deposits", {"lease_id": lid, "kind": "refunded", "amount_cents": 200001, "date": "2026-01-02"}, 409)
        self.post("deposits", {"lease_id": lid, "kind": "refunded", "amount_cents": 50000, "date": "2026-01-02"})
        r = self.client.put("/api/leases/" + str(lid), json={**lease, "end_date": "2020-12-31"})
        self.assertEqual(r.status_code, 200, r.text)
        self.post("units/" + str(u) + "/archive", {})
        self.post("units/" + str(u) + "/restore", {})
        self.assertEqual(len(self.client.get("/api/state").json()["leases"]), 1)

    def test_monthly_constraints_settings_and_restart(self):
        p, u, t = self.setup_portfolio()
        payload = {"property_id": p, "unit_id": u, "month": "2026-09", "amounts": [125050, 5010, 1000, 0, 3000, 4000]}
        rid = self.post("records", payload)["id"]
        self.post("records", payload, 409)
        self.post("records", {**payload, "month": "2026-13"}, 422)
        self.post("records", {**payload, "amounts": [-1, 0, 0, 0, 0, 0]}, 422)
        self.post("records", {**payload, "amounts": [1.5, 0, 0, 0, 0, 0]}, 422)
        self.post("records", {**payload, "amounts": [1, 2]}, 422)
        p2 = self.post("properties", {"name": "Other", "address": "Another", "kind": "Commercial"})["id"]
        self.post("records", {**payload, "property_id": p2}, 422)
        self.post("records", {**payload, "unit_id": None})
        self.post("records", {**payload, "unit_id": None}, 409)
        settings = {"name": "New Owner", "currency": "USD", "timezone": "America/New_York", "category5": "Cleaning", "category6": "Tax"}
        self.assertEqual(self.client.put("/api/settings", json=settings).status_code, 200)
        self.assertEqual(self.client.put("/api/settings", json={**settings, "category5": "Rent"}).status_code, 422)
        self.assertEqual(self.client.put("/api/settings", json={**settings, "currency": "CAD"}).status_code, 409)
        # New application lifespan / database connection, same on-disk state.
        with TestClient(self.main.app) as restarted:
            r = restarted.post("/api/auth/login", json={"email": "owner@example.test", "password": "long-test-password"})
            self.assertEqual(r.status_code, 200)
            state = restarted.get("/api/state").json()
            self.assertEqual(state["settings"]["name"], "New Owner")
            self.assertEqual(state["categories"][4]["name"], "Cleaning")
            self.assertEqual(state["records"][0]["amounts"], payload["amounts"])
            self.assertEqual(len(state["records"]), 2)
        self.assertEqual(self.client.delete("/api/records/" + str(rid)).status_code, 200)

    def test_documents_protected_download_backup_restore(self):
        p, u, t = self.setup_portfolio()
        pdf = b"%PDF-1.4\nMinimal test document\n%%EOF"
        r = self.client.post("/api/documents", files={"file": ("lease.pdf", pdf, "application/pdf")})
        self.assertEqual(r.status_code, 200, r.text)
        id = r.json()["id"]
        r = self.client.put("/api/documents/" + str(id), json={"filename": "lease.pdf", "kind": "Lease", "property_id": p, "unit_id": u, "tenant_id": t})
        self.assertEqual(r.status_code, 200)
        download = self.client.get(f"/api/documents/{id}/download")
        self.assertEqual(download.content, pdf)
        self.assertIn("attachment", download.headers["content-disposition"])
        self.assertEqual(self.client.post("/api/documents", files={"file": ("bad.pdf", b"not PDF")}).status_code, 422)
        self.assertEqual(self.client.post("/api/documents", files={"file": ("bad.html", b"<html>")}).status_code, 422)
        self.assertEqual(self.client.put("/api/documents/" + str(id), json={"filename": "../secret.pdf"}).status_code, 422)
        self.assertEqual(self.client.put("/api/documents/" + str(id), json={"filename": "lease.pdf", "tenant_id": 99999}).status_code, 404)
        folder = self.manage.backup(Path(self.tmp.name) / "backup")
        restore = Path(self.tmp.name) / "restored"
        self.manage.restore(folder, restore)
        with closing(sqlite3.connect(restore / "havenly.sqlite3")) as c:
            storage = c.execute("SELECT storage_name FROM documents WHERE id=?", (id,)).fetchone()[0]
            self.assertEqual(c.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual((restore / "uploads" / storage).read_bytes(), pdf)
        with self.assertRaises(ValueError):
            self.manage.restore(folder, restore)
        self.assertEqual(self.client.delete("/api/documents/" + str(id)).status_code, 200)
        self.assertEqual(self.client.get(f"/api/documents/{id}/download").status_code, 404)
        self.assertTrue((self.db.UPLOADS / storage).exists())
        # Corruption is caught before a destination is created.
        (folder / "uploads" / storage).write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.manage.restore(folder, Path(self.tmp.name) / "bad-restore")

    def test_mixed_use_units(self):
        p = self.post("properties", {"name": "Mixed building", "address": "Test address", "kind": "Mixed"})["id"]
        for kind in ("Residential", "Commercial"):
            u = self.post("units", {"property_id": p, "label": kind, "kind": kind, "notes": "Import note"})["id"]
            state = self.client.get("/api/state").json()
            unit = next(row for row in state["units"] if row["id"] == u)
            self.assertEqual(unit["kind"], kind)
            self.assertEqual(unit["notes"], "Import note")

    def test_rent_notes_and_unit_contact(self):
        p, u, t = self.setup_portfolio()
        response = self.client.put(f"/api/units/{u}", json={"property_id": p, "label": "101", "tenant_id": t, "expected_rent_cents": 200000})
        self.assertEqual(response.status_code, 200, response.text)
        body = {"property_id": p, "unit_id": u, "month": "2026-08", "amounts": [100000, 0, 0, 0, 0, 0], "expected_rent_cents": 200000, "notes": "Half paid.\nBalance promised on the 20th."}
        rid = self.post("records", body)["id"]
        state = self.client.get("/api/state").json()
        record = next(r for r in state["records"] if r["id"] == rid)
        self.assertEqual(record["notes"], body["notes"])
        self.assertEqual(record["expected_rent_cents"], 200000)
        self.assertEqual(record["amounts"][0], 100000)
        self.assertEqual(state["units"][0]["tenant_id"], t)
        self.assertEqual(state["leases"], [])
        self.post("records", {**body, "month": "2026-09", "expected_rent_cents": -1}, code=422)

    def test_migrations_and_origin(self):
        self.db.migrate()
        self.db.migrate()
        with self.db.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 6)
            self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        r = self.client.post("/api/properties", headers={"Origin": "https://attacker.invalid"}, json={"name": "x", "address": "y", "kind": "Apartment"})
        self.assertEqual(r.status_code, 403)

    def test_invalid_form_values(self):
        self.post('tenants', {'name': '   '}, 422)
        self.post('tenants', {'name': 'Test', 'email': 'not-an-email'}, 422)
        p, u, t = self.setup_portfolio()
        self.post('records', {'property_id': p, 'month': '0000-01', 'amounts': [0]*6}, 422)
        self.post('leases', {'unit_id': u, 'tenant_ids': [t], 'start_date': '2026-10-01', 'end_date': '2026-09-01', 'rent_cents': 100}, 422)
        self.post('deposits', {'lease_id': 1, 'kind': 'received', 'amount_cents': 0, 'date': '2026-09-01'}, 422)

    def test_demo_seed_is_fictional_and_requires_empty_portfolio(self):
        from demo_server import seed_demo
        with self.db.connect() as c:
            seed_demo(c)
            self.assertEqual(c.execute('SELECT count(*) FROM leases').fetchone()[0], 3)
            self.assertEqual(c.execute('SELECT count(*) FROM monthly_records').fetchone()[0], 3)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
            with self.assertRaises(ValueError):
                seed_demo(c)

    def test_concurrent_reads_and_writes(self):
        self.setup_portfolio()
        with ThreadPoolExecutor(max_workers=10) as pool:
            reads = list(pool.map(lambda _: self.client.get("/api/state"), range(30)))
            writes = list(pool.map(lambda i: self.client.post("/api/properties", json={
                "name": f"Concurrent {i}", "address": "Test address", "kind": "Commercial"
            }), range(15)))
        self.assertTrue(all(r.status_code == 200 for r in reads + writes))
        self.assertEqual(len(self.client.get("/api/state").json()["properties"]), 16)
        self.assertEqual(len({r.json()["id"] for r in writes}), 15)

    def test_concurrent_deposit_refunds_cannot_overdraw(self):
        p, u, t = self.setup_portfolio()
        lid = self.post("leases", {"unit_id": u, "tenant_ids": [t], "start_date": "2020-01-01",
            "end_date": "2099-01-01", "rent_cents": 100})["id"]
        self.post("deposits", {"lease_id": lid, "kind": "received", "amount_cents": 100, "date": "2026-01-01"})
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.client.post("/api/deposits", json={
                "lease_id": lid, "kind": "refunded", "amount_cents": 100, "date": "2026-01-02"
            }), range(4)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409, 409, 409])

    def test_document_consistency_and_parent_edits(self):
        p, u, t = self.setup_portfolio()
        p2 = self.post("properties", {"name": "Other", "address": "Other", "kind": "Apartment"})["id"]
        u2 = self.post("units", {"property_id": p2, "label": "B"})["id"]
        lease = {"unit_id": u, "tenant_ids": [t], "start_date": "2020-01-01", "end_date": "2099-01-01", "rent_cents": 100}
        lid = self.post("leases", lease)["id"]
        record = {"property_id": p2, "unit_id": u2, "month": "2026-09", "amounts": [100, 0, 0, 0, 0, 0]}
        rid = self.post("records", record)["id"]
        doc = self.client.post("/api/documents", files={"file": ("test.pdf", b"%PDF-1.4 test")}).json()["id"]
        # No explicit property/unit: indirect links still must agree.
        linked = {"filename": "test.pdf", "lease_id": lid, "record_id": rid}
        self.assertEqual(self.client.put(f"/api/documents/{doc}", json=linked).status_code, 422)
        t2 = self.post("tenants", {"name": "Different tenant"})["id"]
        self.assertEqual(self.client.put(f"/api/documents/{doc}", json={
            "filename": "test.pdf", "lease_id": lid, "tenant_id": t2
        }).status_code, 422)
        self.assertEqual(self.client.put(f"/api/records/{rid}", json={**record, "property_id": p, "unit_id": u}).status_code, 200)
        self.assertEqual(self.client.put(f"/api/documents/{doc}", json=linked).status_code, 200)
        # Parent mutations are rolled back if they break an existing document.
        self.assertEqual(self.client.put(f"/api/leases/{lid}", json={**lease, "unit_id": u2}).status_code, 422)
        self.assertEqual(self.client.put(f"/api/records/{rid}", json=record).status_code, 422)
        state = self.client.get("/api/state").json()
        self.assertEqual(state["leases"][0]["unit_id"], u)
        self.assertEqual(state["records"][0]["property_id"], p)

    def test_restore_rejects_missing_manifest_upload(self):
        import json
        self.client.post("/api/documents", files={"file": ("test.pdf", b"%PDF-1.4 test")})
        folder = self.manage.backup(Path(self.tmp.name) / "complete")
        manifest_path = folder / "manifest.json"
        original = json.loads(manifest_path.read_text())
        for key in list(original):
            if key.startswith("uploads/"):
                missing = dict(original)
                del missing[key]
                manifest_path.write_text(json.dumps(missing))
        destination = Path(self.tmp.name) / "incomplete"
        with self.assertRaisesRegex(ValueError, "database-referenced"):
            self.manage.restore(folder, destination)
        self.assertFalse(destination.exists())
        manifest_path.write_text(json.dumps({**original, "../outside": "fake"}))
        with self.assertRaisesRegex(ValueError, "Invalid backup path"):
            self.manage.restore(folder, destination)
        self.assertFalse(destination.exists())

    def test_production_secure_session_and_headers(self):
        os.environ["HAVENLY_ENV"] = "production"
        os.environ["HAVENLY_ORIGIN"] = "https://rentals.example.test"
        try:
            production = importlib.reload(self.main)
            with TestClient(production.app, base_url="https://rentals.example.test") as client:
                response = client.post("/api/auth/login", json={"email": "owner@example.test", "password": "long-test-password"})
                self.assertEqual(response.status_code, 200)
                cookie = response.headers["set-cookie"].lower()
                self.assertIn("secure", cookie)
                self.assertIn("httponly", cookie)
                self.assertIn("samesite=strict", cookie)
                self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
                self.assertEqual(client.get("/api/state").status_code, 200)
                self.assertEqual(client.get("/docs").status_code, 404)
                self.assertEqual(client.get("/openapi.json").status_code, 404)
        finally:
            os.environ.pop("HAVENLY_ENV", None)
            os.environ.pop("HAVENLY_ORIGIN", None)
            importlib.reload(self.main)


if __name__ == "__main__":
    unittest.main()

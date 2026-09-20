import importlib
import os
import sqlite3
import tempfile
import unittest
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

    def test_migrations_and_origin(self):
        self.db.migrate()
        self.db.migrate()
        with self.db.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 1)
            self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        r = self.client.post("/api/properties", headers={"Origin": "https://attacker.invalid"}, json={"name": "x", "address": "y", "kind": "Apartment"})
        self.assertEqual(r.status_code, 403)

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

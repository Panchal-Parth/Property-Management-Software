"""Local-only owner provisioning, import, backups and safe restoration."""
import argparse
import getpass
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from db import DB, UPLOADS, connect, migrate
from security import password_hash


def backup(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    snapshot = destination / "havenly.sqlite3"
    with connect() as source, closing(sqlite3.connect(snapshot)) as target:
        source.backup(target)
    (destination / "uploads").mkdir(mode=0o700)
    with closing(sqlite3.connect(snapshot)) as c:
        for (name,) in c.execute("SELECT storage_name FROM documents"):
            shutil.copy2(UPLOADS / name, destination / "uploads" / name)
        c.execute("DELETE FROM sessions")
        c.execute("DELETE FROM login_attempts")
        c.commit()
    manifest = {}
    for path in destination.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
            manifest[str(path.relative_to(destination))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return destination


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    manifest = json.loads((source / "manifest.json").read_text())
    if not isinstance(manifest, dict):
        raise ValueError("Backup manifest must be an object")
    if "havenly.sqlite3" not in manifest:
        raise ValueError("Backup is missing its database")
    for name, digest in manifest.items():
        # Restrict both source and destination paths; no absolute/traversal keys.
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not (
            name == "havenly.sqlite3" or (len(relative.parts) == 2 and relative.parts[0] == "uploads")
        ):
            raise ValueError("Invalid backup path: " + name)
        path = (source / name).resolve()
        if source not in path.parents or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Backup failed integrity validation: " + name)
    with closing(sqlite3.connect((source / "havenly.sqlite3").as_uri() + "?mode=ro", uri=True)) as c:
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or c.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database integrity check failed")
        for (storage_name,) in c.execute("SELECT storage_name FROM documents"):
            if Path(storage_name).name != storage_name or not storage_name:
                raise ValueError("Invalid document storage name in database")
            if "uploads/" + storage_name not in manifest:
                raise ValueError("Backup is missing a database-referenced upload: " + storage_name)
    if destination.exists():
        raise ValueError("Restore destination must not exist; existing data is never overwritten")
    destination.mkdir(parents=True, mode=0o700)
    (destination / "uploads").mkdir(mode=0o700)
    for name in manifest:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
        target.chmod(0o600)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("create-owner")
    sub.add_parser("reset-password")
    b = sub.add_parser("backup"); b.add_argument("destination")
    r = sub.add_parser("restore"); r.add_argument("source"); r.add_argument("destination")
    i = sub.add_parser("import-legacy"); i.add_argument("source")
    args = parser.parse_args()
    if args.command == "restore":
        restore(args.source, args.destination)
        print("Verified backup restored to a NEW directory. Point HAVENLY_DATA_DIR there before restarting.")
        return
    migrate()
    if args.command in ("create-owner", "reset-password"):
        with connect() as c:
            existing = c.execute("SELECT 1 FROM owners").fetchone()
            if args.command == "create-owner" and existing:
                raise SystemExit("Owner already exists; use reset-password.")
            if args.command == "reset-password" and not existing:
                raise SystemExit("Create an owner first.")
            email = input("Owner email: ").strip().lower() if not existing else None
            name = input("Owner name: ").strip() if not existing else None
            password = getpass.getpass("Password (at least 12 characters): ")
            if len(password) < 12 or len(password) > 256 or password != getpass.getpass("Confirm password: "):
                raise SystemExit("Passwords must match and contain 12–256 characters.")
            if not existing:
                if not name or not email or "@" not in email:
                    raise SystemExit("Enter a name and valid email.")
                c.execute("INSERT INTO owners(id,email,name,password_hash) VALUES (1,?,?,?)", (email, name, password_hash(password)))
            else:
                c.execute("UPDATE owners SET password_hash=? WHERE id=1", (password_hash(password),))
            c.execute("DELETE FROM sessions")
        print("Owner credentials saved; old sessions revoked.")
    elif args.command == "backup":
        print(backup(args.destination))
    elif args.command == "import-legacy":
        with connect() as c, closing(sqlite3.connect(f"file:{Path(args.source).resolve()}?mode=ro", uri=True)) as legacy:
            if c.execute("SELECT 1 FROM properties").fetchone():
                raise SystemExit("Import requires an empty property list to prevent duplicates.")
            for row in legacy.execute("SELECT name,address,property_type,units FROM property"):
                id = c.execute("INSERT INTO properties(name,address,kind) VALUES (?,?,?)", row[:3]).lastrowid
                for n in range(max(1, row[3])):
                    label = "Premises" if row[2] == "Commercial" and row[3] <= 1 else str(n + 1)
                    c.execute("INSERT INTO units(property_id,label) VALUES (?,?)", (id, label))
        print("Legacy properties imported. Original database was not modified.")
    else:
        print("Migrations applied:", DB)


if __name__ == "__main__":
    main()

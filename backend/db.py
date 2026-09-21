"""Versioned, transactional SQLite migrations; paths do not depend on cwd."""
import os
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("HAVENLY_DATA_DIR", str(BASE / "data"))).resolve()
DB = DATA / "havenly.sqlite3"
UPLOADS = DATA / "uploads"


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    # FastAPI may run successive sync dependencies on different worker threads.
    # Connections remain request-local, never shared between concurrent requests.
    c = sqlite3.connect(DB, timeout=20, factory=Connection, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=20000")
    return c


def migrate():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    UPLOADS.mkdir(exist_ok=True, mode=0o700)
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.commit()
        for path in sorted((BASE / "migrations").glob("*.sql")):
            if not c.execute("SELECT 1 FROM schema_migrations WHERE version=?", (path.name,)).fetchone():
                # Migration filenames are repository-owned, never user input.
                # SQLite table rebuilds require foreign keys off outside the transaction.
                # Validate every relationship before committing the rebuilt schema.
                c.execute("PRAGMA foreign_keys=OFF")
                try:
                    c.executescript("BEGIN IMMEDIATE;\n" + path.read_text())
                    if c.execute("PRAGMA foreign_key_check").fetchall():
                        raise ValueError("Migration would break foreign keys: " + path.name)
                    c.execute("INSERT INTO schema_migrations(version) VALUES (?)", (path.name,))
                    c.commit()
                except Exception:
                    c.rollback()
                    raise
                finally:
                    c.execute("PRAGMA foreign_keys=ON")
    DB.chmod(0o600)


def rows(c, sql, args=()):
    return [dict(row) for row in c.execute(sql, args)]

CREATE TABLE admins (
 id INTEGER PRIMARY KEY CHECK (id=1),
 email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE admin_sessions (
 token_hash TEXT PRIMARY KEY,
 admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
 csrf TEXT NOT NULL,
 expires INTEGER NOT NULL
);

CREATE TABLE admin_audit (
 id INTEGER PRIMARY KEY,
 admin_id INTEGER NOT NULL REFERENCES admins(id),
 action TEXT NOT NULL CHECK(action IN ('owner_email_changed','owner_password_changed','owner_email_and_password_changed')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX admin_sessions_expiry ON admin_sessions(expires);

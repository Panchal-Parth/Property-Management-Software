CREATE TABLE owners (
 id INTEGER PRIMARY KEY CHECK (id=1), email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, name TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
 timezone TEXT NOT NULL DEFAULT 'America/New_York', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owners(id),
 csrf TEXT NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE login_attempts (address TEXT NOT NULL, attempted_at INTEGER NOT NULL);
CREATE INDEX login_attempt_time ON login_attempts(attempted_at);
CREATE TABLE properties (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('Apartment','Commercial')), notes TEXT NOT NULL DEFAULT '',
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE units (
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id),
 label TEXT NOT NULL, floor TEXT NOT NULL DEFAULT '', unavailable INTEGER NOT NULL DEFAULT 0 CHECK(unavailable IN (0,1)),
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(property_id,label)
);
CREATE TABLE tenants (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
 emergency_contact TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE leases (
 id INTEGER PRIMARY KEY, unit_id INTEGER NOT NULL REFERENCES units(id),
 start_date TEXT NOT NULL, end_date TEXT NOT NULL CHECK(end_date>=start_date),
 rent_cents INTEGER NOT NULL CHECK(rent_cents>=0), deposit_cents INTEGER NOT NULL DEFAULT 0 CHECK(deposit_cents>=0),
 cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX leases_unit_dates ON leases(unit_id,start_date,end_date);
CREATE TABLE lease_tenants (
 lease_id INTEGER NOT NULL REFERENCES leases(id), tenant_id INTEGER NOT NULL REFERENCES tenants(id),
 PRIMARY KEY(lease_id,tenant_id)
);
CREATE TRIGGER lease_no_overlap_insert BEFORE INSERT ON leases WHEN NEW.cancelled=0
BEGIN
 SELECT RAISE(ABORT,'Lease dates overlap an existing lease') WHERE EXISTS(
 SELECT 1 FROM leases WHERE unit_id=NEW.unit_id AND cancelled=0
 AND start_date<=NEW.end_date AND end_date>=NEW.start_date);
END;
CREATE TRIGGER lease_no_overlap_update BEFORE UPDATE ON leases WHEN NEW.cancelled=0
BEGIN
 SELECT RAISE(ABORT,'Lease dates overlap an existing lease') WHERE EXISTS(
 SELECT 1 FROM leases WHERE id!=NEW.id AND unit_id=NEW.unit_id AND cancelled=0
 AND start_date<=NEW.end_date AND end_date>=NEW.start_date);
END;
CREATE TABLE categories (
 id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 6), name TEXT NOT NULL COLLATE NOCASE UNIQUE,
 kind TEXT NOT NULL CHECK(kind IN ('income','expense')), customizable INTEGER NOT NULL
);
INSERT INTO categories VALUES
 (1,'Rent','income',0),(2,'Water','expense',0),(3,'Repairs','expense',0),
 (4,'Miscellaneous','expense',0),(5,'Insurance','expense',1),(6,'Property tax','expense',1);
CREATE TABLE monthly_records (
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id),
 unit_id INTEGER REFERENCES units(id), month TEXT NOT NULL,
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX monthly_scope ON monthly_records(property_id,ifnull(unit_id,0),month);
CREATE TRIGGER monthly_unit_insert BEFORE INSERT ON monthly_records WHEN NEW.unit_id IS NOT NULL
BEGIN
 SELECT RAISE(ABORT,'Unit belongs to a different property') WHERE NOT EXISTS(
 SELECT 1 FROM units WHERE id=NEW.unit_id AND property_id=NEW.property_id);
END;
CREATE TRIGGER monthly_unit_update BEFORE UPDATE ON monthly_records WHEN NEW.unit_id IS NOT NULL
BEGIN
 SELECT RAISE(ABORT,'Unit belongs to a different property') WHERE NOT EXISTS(
 SELECT 1 FROM units WHERE id=NEW.unit_id AND property_id=NEW.property_id);
END;
CREATE TABLE monthly_amounts (
 record_id INTEGER NOT NULL REFERENCES monthly_records(id) ON DELETE CASCADE,
 category_id INTEGER NOT NULL REFERENCES categories(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>=0),
 PRIMARY KEY(record_id,category_id)
);
CREATE TABLE deposit_transactions (
 id INTEGER PRIMARY KEY, lease_id INTEGER NOT NULL REFERENCES leases(id),
 kind TEXT NOT NULL CHECK(kind IN ('received','refunded','deducted')),
 amount_cents INTEGER NOT NULL CHECK(amount_cents>0), date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE documents (
 id INTEGER PRIMARY KEY, filename TEXT NOT NULL, storage_name TEXT NOT NULL UNIQUE, mime TEXT NOT NULL,
 size INTEGER NOT NULL CHECK(size>0), kind TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
 property_id INTEGER REFERENCES properties(id), unit_id INTEGER REFERENCES units(id),
 tenant_id INTEGER REFERENCES tenants(id), lease_id INTEGER REFERENCES leases(id),
 record_id INTEGER REFERENCES monthly_records(id) ON DELETE SET NULL,
 deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE properties_new (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('Apartment','Commercial','Mixed')), notes TEXT NOT NULL DEFAULT '',
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO properties_new SELECT * FROM properties;
DROP TABLE properties;
ALTER TABLE properties_new RENAME TO properties;
ALTER TABLE units ADD COLUMN kind TEXT NOT NULL DEFAULT 'Residential' CHECK(kind IN ('Residential','Commercial'));
ALTER TABLE units ADD COLUMN notes TEXT NOT NULL DEFAULT '';
UPDATE units SET kind='Commercial' WHERE property_id IN (SELECT id FROM properties WHERE kind='Commercial');

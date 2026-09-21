-- A contact/rent on file is not a lease: dates remain unknown until entered.
ALTER TABLE units ADD COLUMN tenant_id INTEGER REFERENCES tenants(id);
ALTER TABLE units ADD COLUMN expected_rent_cents INTEGER CHECK(expected_rent_cents IS NULL OR expected_rent_cents>=0);
ALTER TABLE monthly_records ADD COLUMN expected_rent_cents INTEGER CHECK(expected_rent_cents IS NULL OR expected_rent_cents>=0);

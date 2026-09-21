CREATE TABLE IF NOT EXISTS workbook_imports (
 source_hash TEXT PRIMARY KEY, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 source_rows_json TEXT NOT NULL, summary_json TEXT NOT NULL
);

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS vehicles (
  id                   TEXT PRIMARY KEY,
  registration_number  TEXT,
  vin                  TEXT,
  description          TEXT,
  created_at           TEXT,
  fs_mtime             REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicles_registration
  ON vehicles(registration_number) WHERE registration_number IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicles_vin
  ON vehicles(vin) WHERE vin IS NOT NULL;

CREATE VIRTUAL TABLE IF NOT EXISTS vehicles_fts USING fts5(
  registration_number, vin, description,
  content='vehicles', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS vehicles_fts_ai AFTER INSERT ON vehicles BEGIN
  INSERT INTO vehicles_fts(rowid, registration_number, vin, description)
  VALUES (new.rowid, new.registration_number, new.vin, new.description);
END;

CREATE TRIGGER IF NOT EXISTS vehicles_fts_ad AFTER DELETE ON vehicles BEGIN
  INSERT INTO vehicles_fts(vehicles_fts, rowid, registration_number, vin, description)
  VALUES('delete', old.rowid, old.registration_number, old.vin, old.description);
END;

CREATE TRIGGER IF NOT EXISTS vehicles_fts_au AFTER UPDATE ON vehicles BEGIN
  INSERT INTO vehicles_fts(vehicles_fts, rowid, registration_number, vin, description)
  VALUES('delete', old.rowid, old.registration_number, old.vin, old.description);
  INSERT INTO vehicles_fts(rowid, registration_number, vin, description)
  VALUES (new.rowid, new.registration_number, new.vin, new.description);
END;

CREATE TABLE IF NOT EXISTS repairs (
  id                   TEXT PRIMARY KEY,
  vehicle_id           TEXT NOT NULL,
  date                 TEXT NOT NULL,
  description          TEXT,
  folder_name          TEXT NOT NULL,
  fs_mtime             REAL
);
CREATE INDEX IF NOT EXISTS idx_repairs_vehicle_date
  ON repairs(vehicle_id, date DESC);

CREATE TABLE IF NOT EXISTS images (
  id            TEXT PRIMARY KEY,
  repair_id     TEXT NOT NULL,
  filename      TEXT NOT NULL,
  thumb_path    TEXT,
  mime_type     TEXT,
  size_bytes    INTEGER,
  exif_taken_at TEXT,
  fs_mtime      REAL
);
CREATE INDEX IF NOT EXISTS idx_images_repair ON images(repair_id);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

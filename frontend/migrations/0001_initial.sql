-- RiceGrade D1 schema; account data is distinct from unfinished ML inference.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('operator', 'qa')),
  password_hash TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  password_iterations INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS password_resets (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);

CREATE TABLE IF NOT EXISTS login_attempts (
  email_key TEXT PRIMARY KEY,
  attempts INTEGER NOT NULL DEFAULT 0,
  window_start TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lot_id TEXT NOT NULL,
  test_run_id TEXT NOT NULL,
  test_date TEXT NOT NULL,
  paddy_input_weight REAL NOT NULL CHECK(paddy_input_weight > 0),
  total_milled_rice_weight REAL NOT NULL CHECK(total_milled_rice_weight > 0),
  brown_rice_weight REAL,
  head_rice_weight REAL,
  moisture_content REAL,
  machine_notes TEXT NOT NULL DEFAULT '',
  total_milling_recovery REAL NOT NULL,
  brown_rice_recovery REAL,
  head_rice_recovery REAL,
  status TEXT NOT NULL DEFAULT 'awaiting_model',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, test_run_id),
  CHECK(total_milled_rice_weight <= paddy_input_weight),
  CHECK(brown_rice_weight IS NULL OR (brown_rice_weight >= total_milled_rice_weight AND brown_rice_weight <= paddy_input_weight)),
  CHECK(head_rice_weight IS NULL OR (head_rice_weight > 0 AND head_rice_weight <= total_milled_rice_weight)),
  CHECK(moisture_content IS NULL OR (moisture_content > 0 AND moisture_content <= 100))
);
CREATE INDEX IF NOT EXISTS idx_assessments_owner ON assessments(user_id, created_at DESC, id DESC);

-- Image BYTES are stored in private R2 objects, never D1 or public pages.
CREATE TABLE IF NOT EXISTS assessment_images (
  assessment_id INTEGER PRIMARY KEY REFERENCES assessments(id) ON DELETE CASCADE,
  object_key TEXT NOT NULL,
  media_type TEXT NOT NULL,
  filename TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  uploaded_at TEXT NOT NULL
);

-- Future reports remain ungenerated until a validated model and DSS exist.
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL UNIQUE REFERENCES assessments(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  content_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

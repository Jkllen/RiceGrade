-- Research-only inference result records, one per assessment/image. Not official grading.
CREATE TABLE IF NOT EXISTS screening_trials (
  assessment_id INTEGER PRIMARY KEY REFERENCES assessments(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('processing','research_preview','failed')),
  result_json TEXT,
  error_message TEXT,
  model_version TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_screening_trials_status ON screening_trials(status);

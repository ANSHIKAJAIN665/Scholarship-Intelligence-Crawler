-- Canonical logical schema; SQLAlchemy creates these four tables on startup.
-- See database/models.py for the executable SQLite schema.
CREATE TABLE scholarships (
  id TEXT PRIMARY KEY,
  scholarship_name TEXT NOT NULL,
  provider TEXT NOT NULL,
  official_source_url TEXT NOT NULL,
  application_url TEXT NOT NULL,
  source_type TEXT NOT NULL,
  amount TEXT NOT NULL,
  benefit TEXT NOT NULL,
  eligibility TEXT NOT NULL,
  academic_requirements TEXT NOT NULL,
  education_level TEXT NOT NULL,
  course_requirements TEXT NOT NULL,
  income_criteria TEXT NOT NULL,
  age_criteria TEXT NOT NULL,
  gender_criteria TEXT NOT NULL,
  category_criteria TEXT NOT NULL,
  domicile_requirements TEXT NOT NULL,
  institution_requirements TEXT NOT NULL,
  opening_date TEXT NOT NULL,
  closing_date TEXT NOT NULL,
  documents_required TEXT NOT NULL,
  selection_process TEXT NOT NULL,
  renewal_requirements TEXT NOT NULL,
  current_status TEXT NOT NULL,
  confidence_score INTEGER NOT NULL,
  verification_status TEXT NOT NULL,
  score_breakdown_json TEXT NOT NULL,
  last_verified TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE crawl_runs (
  id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT NOT NULL,
  discovered_count INTEGER NOT NULL, new_count INTEGER NOT NULL,
  updated_count INTEGER NOT NULL, changed_count INTEGER NOT NULL,
  expired_count INTEGER NOT NULL, failed_count INTEGER NOT NULL,
  status TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE source_evidence (
  id TEXT PRIMARY KEY, scholarship_id TEXT NOT NULL REFERENCES scholarships(id),
  field_name TEXT NOT NULL, extracted_value TEXT NOT NULL,
  evidence_text TEXT NOT NULL, source_url TEXT NOT NULL, captured_at TEXT NOT NULL
);
CREATE TABLE change_history (
  id TEXT PRIMARY KEY, scholarship_id TEXT NOT NULL REFERENCES scholarships(id),
  field_changed TEXT NOT NULL, old_value TEXT NOT NULL, new_value TEXT NOT NULL,
  date_detected TEXT NOT NULL, source_url TEXT NOT NULL, evidence TEXT NOT NULL,
  is_demo BOOLEAN NOT NULL DEFAULT FALSE
);

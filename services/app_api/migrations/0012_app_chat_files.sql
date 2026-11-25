-- Files the agent attaches to a private app chat answer (a run's picture or sheet, a dynamic working's result;
-- src/ultron/tools/files.py). Stored as base64 text in D1 (a row is at most 2 MB, so a file is at most 1.4 MB),
-- not in R2: the R2 bucket is kept for app releases under its free-allowance guards. Kept 30 days.
CREATE TABLE app_chat_file (
  id TEXT PRIMARY KEY NOT NULL,
  job_id TEXT NOT NULL REFERENCES app_chat_job(id) ON DELETE CASCADE,
  name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
  mime TEXT NOT NULL,
  caption TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL CHECK(size BETWEEN 1 AND 1400000),
  data TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX app_chat_file_job ON app_chat_file(job_id);
-- One-use, five-minute download links, so the phone's browser can save a file without the session token.
CREATE TABLE app_chat_file_ticket (
  token_hash TEXT PRIMARY KEY NOT NULL,
  file_id TEXT NOT NULL REFERENCES app_chat_file(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
);

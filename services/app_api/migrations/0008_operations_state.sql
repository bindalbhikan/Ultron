-- Atomic claims shared by Telegram and app decisions; ambiguous dispatches are never retried automatically.
CREATE TABLE agent_approval (
  id TEXT PRIMARY KEY NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','dispatching','completed','rejected','uncertain')),
  expires INTEGER NOT NULL
);
CREATE INDEX agent_approval_expiry ON agent_approval(expires);

-- Every phone job has its own row: overlapping workings cannot overwrite each other.
CREATE TABLE phone_job (
  id TEXT PRIMARY KEY NOT NULL,
  kind TEXT NOT NULL,
  items TEXT NOT NULL,
  created INTEGER NOT NULL,
  taken INTEGER NOT NULL DEFAULT 0,
  done INTEGER NOT NULL DEFAULT 0,
  expires INTEGER NOT NULL
);
CREATE INDEX phone_job_queue ON phone_job(done, created);
CREATE TABLE phone_result (
  job_id TEXT NOT NULL REFERENCES phone_job(id) ON DELETE CASCADE,
  part INTEGER NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY(job_id,part)
);

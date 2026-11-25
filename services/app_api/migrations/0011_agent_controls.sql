CREATE TABLE agent_schedule (
  id TEXT PRIMARY KEY NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  cron TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL,
  updated_by TEXT NOT NULL,
  change_id TEXT NOT NULL
);
CREATE TABLE agent_schedule_history (
  change_id TEXT PRIMARY KEY NOT NULL,
  id TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  cron TEXT,
  created_at INTEGER NOT NULL,
  revision INTEGER NOT NULL
);
CREATE TABLE agent_control_event (
  id TEXT PRIMARY KEY NOT NULL,
  actor TEXT NOT NULL,
  operation TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

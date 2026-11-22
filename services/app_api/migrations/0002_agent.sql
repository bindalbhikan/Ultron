-- The agent's memory and settings, in the same D1 database as the app's users ("ultron"): the
-- Telegram worker (worker/agent.js, binding AGENT_DB) reads and writes them for the Python agent,
-- the app API (binding DB) shows them in the control panel.

-- long-term notes (ultron.core.memory): preferences, facts, known issues, decisions, incidents
CREATE TABLE agent_note (
  id TEXT PRIMARY KEY NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('preference', 'fact', 'known_issue', 'decision', 'incident')),
  text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 2000),
  tags TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL DEFAULT '',
  uses INTEGER NOT NULL DEFAULT 0,
  created INTEGER NOT NULL,          -- unix seconds
  updated INTEGER NOT NULL
);
CREATE INDEX agent_note_trim ON agent_note(kind, uses, updated);

-- the last messages of each Telegram chat, for follow-up questions
CREATE TABLE agent_turn (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat TEXT NOT NULL,
  at INTEGER NOT NULL,               -- unix seconds
  q TEXT NOT NULL,
  a TEXT NOT NULL
);
CREATE INDEX agent_turn_chat ON agent_turn(chat, id);

-- what the control panel sets: model ("auto" or "provider:model"), tier, order (JSON values);
-- the Python agent reads them through the worker's GET /api/settings
CREATE TABLE agent_setting (
  key TEXT PRIMARY KEY NOT NULL CHECK (key IN ('model', 'tier', 'order')),
  value TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL,       -- unix milliseconds
  updated_by TEXT REFERENCES user(id) ON DELETE SET NULL
);

-- agent.manage: change the model settings; memory.manage: drop the agent's notes. The admin role is
-- a system role (its trigger refuses changes), so the trigger is lifted for this one update.
DROP TRIGGER immutable_system_roles;
UPDATE app_role SET permissions = json_insert(permissions, '$[#]', 'agent.manage', '$[#]', 'memory.manage'),
  revision = revision + 1, updated_at = unixepoch() * 1000 WHERE id = 'admin';
CREATE TRIGGER immutable_system_roles BEFORE UPDATE ON app_role
WHEN OLD.id IN ('admin','pending')
BEGIN SELECT RAISE(ABORT, 'system_role'); END;

-- Private app conversations, processed by the existing Python agent without action tools.
CREATE TABLE app_chat_job (
  id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  question TEXT NOT NULL CHECK(length(question) BETWEEN 1 AND 2000),
  answer TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX app_chat_history ON app_chat_job(user_id, created_at);
CREATE UNIQUE INDEX app_chat_pending ON app_chat_job(user_id) WHERE status IN ('queued','running');

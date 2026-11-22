-- Agent mode phones (the ULTRON app on Android): a phone that does work for the bots on its own line, such as
-- the Myntra style lookups of zero TD. An administrator signed in on the phone turns it on; the app API makes a
-- token for that phone and keeps only its SHA-256 here. The Telegram worker accepts the token on its phone
-- routes (/api/phone/next, /api/phone/result) while it is not revoked; the control panel revokes it.
CREATE TABLE phone_agent (
  id TEXT PRIMARY KEY NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,               -- hex SHA-256 of the token; the token itself is never stored
  device TEXT NOT NULL,                          -- what the phone reported (maker, model)
  created_by TEXT REFERENCES user(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL,                   -- unix milliseconds
  last_seen INTEGER NOT NULL DEFAULT 0,
  revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
);

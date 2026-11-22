-- The agent's model API keys, added in the app's control panel (Brain): several per provider, used in turn.
-- The key itself is AES-GCM encrypted with KEYS_SECRET (a secret of both the app API and the Telegram worker);
-- the app shows only its last four characters. The worker hands the keys to the Python agent (its token),
-- and the agent reports a key that hit its limit (resting until a time) or was refused (bad).
CREATE TABLE api_key (
  id TEXT PRIMARY KEY NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('anthropic', 'openai', 'google', 'nvidia', 'groq')),
  label TEXT NOT NULL DEFAULT '',
  iv TEXT NOT NULL,                              -- base64 AES-GCM nonce
  ciphertext TEXT NOT NULL,                      -- base64 AES-GCM of the key
  last4 TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,           -- order within the provider: lower is tried first
  status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'limit', 'bad')),
  resting_until INTEGER NOT NULL DEFAULT 0,      -- unix ms: a key at its limit is skipped until then
  last_error TEXT NOT NULL DEFAULT '',
  last_used INTEGER NOT NULL DEFAULT 0,
  created_by TEXT REFERENCES user(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX api_key_provider ON api_key(provider, position, created_at);

-- the models each provider offers, as the agent last read them (GET /models), for the model picker
CREATE TABLE agent_model (
  provider TEXT PRIMARY KEY NOT NULL,
  ids TEXT NOT NULL CHECK (json_valid(ids)),
  updated_at INTEGER NOT NULL                    -- unix ms
);

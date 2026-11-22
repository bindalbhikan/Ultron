-- The phones that send their SMS to the SMS sheet ("SMS only" mode of the Ultron app): no account,
-- only a name the person types and a random id the app makes once. The Telegram worker
-- (worker/agent.js POST /api/sms) records each phone here and passes its SMS to the sheet's Apps
-- Script with the secret only the worker holds; the control panel lists the phones and blocks one.
CREATE TABLE sms_phone (
  id TEXT PRIMARY KEY NOT NULL,                  -- the app's random id (UUID)
  name TEXT NOT NULL,                            -- what the person typed: goes in the sheet's User column
  first_seen INTEGER NOT NULL,                   -- unix milliseconds
  last_seen INTEGER NOT NULL,
  sent INTEGER NOT NULL DEFAULT 0,               -- SMS the sheet took
  hour INTEGER NOT NULL DEFAULT 0,               -- the hour (unix ms / 3600000) of hour_count
  hour_count INTEGER NOT NULL DEFAULT 0,         -- SMS in that hour, for the rate limit
  blocked INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0, 1)),
  app_version TEXT NOT NULL DEFAULT '',
  revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX sms_phone_seen ON sms_phone(last_seen DESC);

-- phone.manage now also covers these phones (it was already in the admin and manager roles)

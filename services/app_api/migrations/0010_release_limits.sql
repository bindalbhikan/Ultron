-- Conservative, durable accounting. Never reset storage reservations automatically.
CREATE TABLE release_usage (
  period TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('A','B')),
  used INTEGER NOT NULL,
  PRIMARY KEY(period,kind)
);
CREATE TABLE release_upload (
  id TEXT PRIMARY KEY NOT NULL,
  object_key TEXT NOT NULL,
  size INTEGER NOT NULL CHECK(size>0),
  upload_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed')),
  created INTEGER NOT NULL
);
CREATE INDEX release_upload_lookup ON release_upload(object_key,upload_id);

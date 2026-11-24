-- The current completed R2 build per platform; an older CI run cannot replace a newer release.
CREATE TABLE app_release (
  platform TEXT PRIMARY KEY NOT NULL,
  version TEXT NOT NULL,
  build INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  size INTEGER NOT NULL,
  object_key TEXT NOT NULL,
  published INTEGER NOT NULL
);

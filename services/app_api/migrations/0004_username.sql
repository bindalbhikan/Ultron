-- Sign-in by username (better-auth's username plugin). The plugin keeps the lower-case form in
-- `username` (unique) and the form the person typed in `display_username`. An account made without an
-- email gets an internal address <username>@users.ultron.invalid (the reserved .invalid domain: never mailed).
ALTER TABLE user ADD COLUMN username TEXT;
ALTER TABLE user ADD COLUMN display_username TEXT;
CREATE UNIQUE INDEX user_username_unique ON user(username);

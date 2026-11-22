CREATE TABLE user (
  id TEXT PRIMARY KEY NOT NULL,
  name TEXT NOT NULL,
  email TEXT NOT NULL COLLATE NOCASE UNIQUE,
  email_verified INTEGER NOT NULL DEFAULT 0,
  image TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE session (
  id TEXT PRIMARY KEY NOT NULL,
  expires_at INTEGER NOT NULL,
  token TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  ip_address TEXT,
  user_agent TEXT,
  user_id TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE
);
CREATE INDEX session_user_idx ON session(user_id);
CREATE TABLE account (
  id TEXT PRIMARY KEY NOT NULL,
  account_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  access_token TEXT,
  refresh_token TEXT,
  id_token TEXT,
  access_token_expires_at INTEGER,
  refresh_token_expires_at INTEGER,
  scope TEXT,
  password TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX account_user_idx ON account(user_id);
CREATE UNIQUE INDEX account_provider_idx ON account(provider_id, account_id);
CREATE TABLE verification (
  id TEXT PRIMARY KEY NOT NULL,
  identifier TEXT NOT NULL,
  value TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX verification_identifier_idx ON verification(identifier);
CREATE TABLE rate_limit (
  id TEXT PRIMARY KEY NOT NULL,
  key TEXT NOT NULL UNIQUE,
  count INTEGER NOT NULL,
  last_request INTEGER NOT NULL
);
CREATE TABLE app_role (
  id TEXT PRIMARY KEY NOT NULL,
  name TEXT NOT NULL,
  permissions TEXT NOT NULL CHECK(json_valid(permissions) AND json_type(permissions) = 'array'),
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);
CREATE TABLE app_access (
  user_id TEXT PRIMARY KEY NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','disabled')),
  role_id TEXT NOT NULL DEFAULT 'pending' REFERENCES app_role(id),
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);
CREATE INDEX app_access_role_status_idx ON app_access(role_id, status);
CREATE TABLE app_audit (
  id TEXT PRIMARY KEY NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  target_id TEXT NOT NULL,
  detail TEXT NOT NULL CHECK(json_valid(detail)),
  created_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);
CREATE INDEX app_audit_created_idx ON app_audit(created_at DESC);

INSERT INTO app_role(id,name,permissions) VALUES
('admin','Administrator','["app.access","reports.read","workflows.read","workflows.run","approvals.read","approvals.decide","analytics.read","connections.read","phone.manage","schedule.read","agent.chat","agent.tools.read","agent.tools.execute","users.manage","roles.manage"]'),
('manager','Manager','["app.access","reports.read","workflows.read","workflows.run","approvals.read","approvals.decide","analytics.read","connections.read","phone.manage","schedule.read","agent.chat","agent.tools.read"]'),
('operator','Operator','["app.access","reports.read","workflows.read","workflows.run","approvals.read","schedule.read","agent.chat"]'),
('viewer','Viewer','["app.access","reports.read","workflows.read","analytics.read","schedule.read"]'),
('pending','Awaiting approval','[]');

CREATE TRIGGER register_pending AFTER INSERT ON user BEGIN
  INSERT INTO app_access(user_id) VALUES(NEW.id);
END;
CREATE TRIGGER retain_last_admin BEFORE UPDATE OF status,role_id ON app_access
WHEN OLD.status = 'active' AND OLD.role_id = 'admin'
  AND (NEW.status != 'active' OR NEW.role_id != 'admin')
  AND (SELECT count(*) FROM app_access WHERE status='active' AND role_id='admin') <= 1
BEGIN SELECT RAISE(ABORT, 'last_admin'); END;
CREATE TRIGGER retain_last_admin_on_delete BEFORE DELETE ON app_access
WHEN OLD.status='active' AND OLD.role_id='admin'
  AND (SELECT count(*) FROM app_access WHERE status='active' AND role_id='admin') <= 1
BEGIN SELECT RAISE(ABORT, 'last_admin'); END;
CREATE TRIGGER immutable_system_roles BEFORE UPDATE ON app_role
WHEN OLD.id IN ('admin','pending')
BEGIN SELECT RAISE(ABORT, 'system_role'); END;
CREATE TRIGGER revoke_access_sessions AFTER UPDATE OF status,role_id ON app_access BEGIN
  DELETE FROM session WHERE user_id=NEW.user_id;
END;
CREATE TRIGGER revoke_role_sessions AFTER UPDATE OF permissions ON app_role BEGIN
  DELETE FROM session WHERE user_id IN (SELECT user_id FROM app_access WHERE role_id=NEW.id);
END;

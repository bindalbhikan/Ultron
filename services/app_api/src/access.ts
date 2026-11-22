import type { Env } from './auth';

export const PERMISSIONS = [
  'app.access', 'reports.read', 'workflows.read', 'workflows.run', 'approvals.read', 'approvals.decide',
  'analytics.read', 'connections.read', 'phone.manage', 'schedule.read', 'agent.chat', 'agent.tools.read',
  'agent.tools.execute', 'users.manage', 'roles.manage',
] as const;
export type Permission = typeof PERMISSIONS[number];
export type AccessStatus = 'pending' | 'active' | 'disabled';
export interface Identity {
  id: string; name: string; email: string; emailVerified: boolean;
  status: AccessStatus; roleId: string; roleName: string; revision: number; permissions: string[];
}
export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function identity(env: Env, id: string): Promise<Identity> {
  const row = await env.DB.prepare(`SELECT u.id,u.name,u.email,u.email_verified,a.status,a.role_id,a.revision,
    r.name AS role_name,r.permissions FROM user u JOIN app_access a ON a.user_id=u.id
    JOIN app_role r ON r.id=a.role_id WHERE u.id=?`).bind(id).first<{
      id: string; name: string; email: string; email_verified: number; status: AccessStatus;
      role_id: string; revision: number; role_name: string; permissions: string;
    }>();
  if (!row) throw new HttpError(403, 'Account access is unavailable.');
  return { id: row.id, name: row.name, email: row.email, emailVerified: Boolean(row.email_verified),
    status: row.status, roleId: row.role_id, roleName: row.role_name, revision: row.revision,
    permissions: row.status === 'active' ? JSON.parse(row.permissions) : [] };
}
export function requirePermission(user: Identity, permission: Permission) {
  if (user.status !== 'active' || !user.permissions.includes('app.access') || !user.permissions.includes(permission)) {
    throw new HttpError(403, 'Your administrator has not granted this access.');
  }
}
export function rolePermissions(input: unknown): string[] {
  if (!Array.isArray(input) || !input.every((p) => typeof p === 'string' && PERMISSIONS.includes(p as Permission))) {
    throw new HttpError(400, 'Select valid permissions.');
  }
  return [...new Set(input)].sort();
}

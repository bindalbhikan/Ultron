import 'package:flutter/foundation.dart';

const accessPermissions = <String, String>{
  'app.access': 'Open the app',
  'reports.read': 'View reports',
  'workflows.read': 'View workflows',
  'workflows.run': 'Request workflow runs',
  'approvals.read': 'View approvals',
  'approvals.decide': 'Approve or decline changes',
  'analytics.read': 'View analytics',
  'connections.read': 'View portal connections',
  'phone.manage': 'Manage Phone Work',
  'schedule.read': 'View schedules',
  'agent.chat': 'Chat with the agent',
  'agent.tools.read': 'Read agent tool results',
  'agent.tools.execute': 'Execute agent tools',
  'users.manage': 'Manage users and assign access (privileged)',
  'roles.manage': 'Create and edit role permissions (privileged)',
};

String? permissionForPath(String path) => switch (path) {
  '/app/agent' => 'agent.chat',
  '/app/workflows' => 'workflows.read',
  '/app/reports' => 'reports.read',
  '/app/approvals' => 'approvals.read',
  '/app/analytics' => 'analytics.read',
  '/app/phone' => 'phone.manage',
  '/app/connections' => 'connections.read',
  '/app/schedule' => 'schedule.read',
  '/app/admin' => 'users.manage',
  '/app/roles' => 'roles.manage',
  _ => null,
};

@immutable
class AppUser {
  const AppUser({required this.id, required this.name, required this.email,
    required this.status, required this.roleId, required this.roleName,
    required this.revision, this.emailVerified = false, this.permissions = const []});
  final String id, name, email, status, roleId, roleName;
  final int revision;
  final bool emailVerified;
  final List<String> permissions;
  bool allows(String permission) => status == 'active' && permissions.contains('app.access') && permissions.contains(permission);
  bool get hasAppAccess => allows('app.access');
  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
    id: json['id'] as String, name: json['name'] as String, email: json['email'] as String,
    status: json['status'] as String, roleId: json['roleId'] as String, roleName: json['roleName'] as String,
    revision: json['revision'] as int, emailVerified: json['emailVerified'] == true || json['emailVerified'] == 1,
    permissions: List<String>.from(json['permissions'] as List? ?? const []));
}

@immutable
class AccessRole {
  const AccessRole({required this.id, required this.name, required this.permissions, required this.revision});
  final String id, name;
  final List<String> permissions;
  final int revision;
  bool get immutable => id == 'admin' || id == 'pending';
  factory AccessRole.fromJson(Map<String, dynamic> json) => AccessRole(
    id: json['id'] as String, name: json['name'] as String,
    permissions: List<String>.from(json['permissions'] as List), revision: json['revision'] as int);
}

class UserPage {
  const UserPage(this.users, {this.hasMore = false});
  final List<AppUser> users;
  final bool hasMore;
}

const demoAdmin = AppUser(id: 'demo-admin', name: 'Workspace owner', email: 'owner@example.com',
  status: 'active', roleId: 'admin', roleName: 'Administrator', revision: 1,
  permissions: ['app.access','reports.read','workflows.read','workflows.run','approvals.read','approvals.decide',
    'analytics.read','connections.read','phone.manage','schedule.read','agent.chat','agent.tools.read',
    'agent.tools.execute','users.manage','roles.manage']);

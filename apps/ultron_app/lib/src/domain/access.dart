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
  'agent.manage': 'Change the agent\'s model settings (privileged)',
  'memory.manage': 'Remove notes from the agent\'s memory',
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
  '/app/control' => 'agent.tools.read',
  _ => null,
};

@immutable
class AppUser {
  const AppUser({
    required this.id,
    required this.name,
    required this.email,
    required this.status,
    required this.roleId,
    required this.roleName,
    required this.revision,
    this.emailVerified = false,
    this.permissions = const [],
  });
  final String id, name, email, status, roleId, roleName;
  final int revision;
  final bool emailVerified;
  final List<String> permissions;
  bool allows(String permission) =>
      status == 'active' &&
      permissions.contains('app.access') &&
      permissions.contains(permission);
  bool get hasAppAccess => allows('app.access');
  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
    id: json['id'] as String,
    name: json['name'] as String,
    email: json['email'] as String,
    status: json['status'] as String,
    roleId: json['roleId'] as String,
    roleName: json['roleName'] as String,
    revision: json['revision'] as int,
    emailVerified: json['emailVerified'] == true || json['emailVerified'] == 1,
    permissions: List<String>.from(json['permissions'] as List? ?? const []),
  );
}

@immutable
class AccessRole {
  const AccessRole({
    required this.id,
    required this.name,
    required this.permissions,
    required this.revision,
  });
  final String id, name;
  final List<String> permissions;
  final int revision;
  bool get immutable => id == 'admin' || id == 'pending';
  factory AccessRole.fromJson(Map<String, dynamic> json) => AccessRole(
    id: json['id'] as String,
    name: json['name'] as String,
    permissions: List<String>.from(json['permissions'] as List),
    revision: json['revision'] as int,
  );
}

class UserPage {
  const UserPage(this.users, {this.hasMore = false});
  final List<AppUser> users;
  final bool hasMore;
}

const demoAdmin = AppUser(
  id: 'demo-admin',
  name: 'Workspace owner',
  email: 'owner@example.com',
  status: 'active',
  roleId: 'admin',
  roleName: 'Administrator',
  revision: 1,
  permissions: [
    'app.access',
    'reports.read',
    'workflows.read',
    'workflows.run',
    'approvals.read',
    'approvals.decide',
    'analytics.read',
    'connections.read',
    'phone.manage',
    'schedule.read',
    'agent.chat',
    'agent.tools.read',
    'agent.tools.execute',
    'users.manage',
    'roles.manage',
    'agent.manage',
    'memory.manage',
  ],
);

/// The agent's model settings (services/app_api /api/agent/settings): what the Python agent uses
/// within 5 minutes, unless its AGENT_MODEL* variables are set.
@immutable
class AgentSettings {
  const AgentSettings({
    required this.model,
    required this.tier,
    required this.order,
    required this.revision,
    this.providers = const [],
    this.tiers = const ['smart', 'fast'],
  });
  final String model, tier;
  final List<String> order, providers, tiers;
  final int revision;
  bool get auto => model == 'auto';
  factory AgentSettings.fromJson(Map<String, dynamic> json) => AgentSettings(
    model: json['model'] as String,
    tier: json['tier'] as String,
    order: List<String>.from(json['order'] as List),
    revision: (json['revision'] as num).toInt(),
    providers: List<String>.from(json['providers'] as List? ?? const []),
    tiers: List<String>.from(json['tiers'] as List? ?? const ['smart', 'fast']),
  );
}

const providerLabels = <String, String>{
  'anthropic': 'Anthropic (Claude)',
  'openai': 'OpenAI',
  'google': 'Google AI Studio (Gemini)',
  'nvidia': 'NVIDIA',
  'groq': 'Groq',
  'cloudflare': 'Cloudflare Workers AI (free)',
};

/// One long-term note of the agent's memory.
@immutable
class AgentNote {
  const AgentNote({
    required this.id,
    required this.kind,
    required this.text,
    required this.tags,
    required this.source,
    required this.uses,
    required this.updated,
  });
  final String id, kind, text, source;
  final List<String> tags;
  final int uses;
  final DateTime updated;
  factory AgentNote.fromJson(Map<String, dynamic> json) => AgentNote(
    id: json['id'] as String,
    kind: json['kind'] as String,
    text: json['text'] as String,
    tags: List<String>.from(json['tags'] as List? ?? const []),
    source: json['source'] as String? ?? '',
    uses: (json['uses'] as num? ?? 0).toInt(),
    updated: DateTime.fromMillisecondsSinceEpoch(
      (json['updated'] as num? ?? 0).toInt() * 1000,
    ),
  );
}

class AgentMemory {
  const AgentMemory(this.notes, {this.counts = const {}});
  final List<AgentNote> notes;
  final Map<String, int> counts;
}

const noteKinds = <String, String>{
  'preference': 'Preferences',
  'fact': 'Facts',
  'decision': 'Decisions',
  'known_issue': 'Known issues',
  'incident': 'Incidents',
};

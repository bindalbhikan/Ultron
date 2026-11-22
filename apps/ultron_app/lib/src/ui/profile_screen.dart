import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../domain/models.dart';
import '../app_info.dart';
import '../state/providers.dart';
import 'actions.dart';
import 'components.dart';
import 'account_screen.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => DataGate(
    builder: (data) => PageBody(
      maxWidth: 900,
      children: [
        Row(
          children: [
            CircleAvatar(
              radius: 29,
              backgroundColor: Theme.of(context).colorScheme.primary
                  .withValues(alpha: .1),
              child: Text(
                'OW',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Workspace owner',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  Text(
                    'Demo workspace',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 25),
        EmeraldPanel(
          padding: const EdgeInsets.all(21),
          child: Row(
            children: [
              const Icon(LucideIcons.lockKeyhole, size: 29),
              const SizedBox(width: 16),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Workspace access',
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 16,
                      ),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'Owner',
                      style: TextStyle(fontSize: 12, color: Color(0xFFD8F4E5)),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Account security',
                onPressed: () => _security(context, ref),
                icon: const Icon(LucideIcons.chevronRight),
              ),
            ],
          ),
        ),
        const SectionHeading('Connections'),
        Card(
          child: Column(
            children: [
              for (final connection in data.connections.take(4))
                _ConnectionRow(connection: connection),
            ],
          ),
        ),
        const SizedBox(height: 22),
        for (final destination in <(String, IconData, VoidCallback)>[
          if(canAccess(ref,'users.manage'))('User management',LucideIcons.users,()=>context.go('/app/admin')),
          if(canAccess(ref,'roles.manage'))('Roles & permissions',LucideIcons.shieldCheck,()=>context.go('/app/roles')),
          (
            'Phone Work',
            LucideIcons.smartphone,
            () => context.go('/app/phone'),
          ),
          (
            'Run analytics',
            LucideIcons.chartNoAxesCombined,
            () => context.go('/app/analytics'),
          ),
          (
            'Approvals',
            LucideIcons.shieldCheck,
            () => context.go('/app/approvals'),
          ),
          (
            'Schedule',
            LucideIcons.calendarDays,
            () => context.go('/app/schedule'),
          ),
          (
            'All connections',
            LucideIcons.plug,
            () => context.go('/app/connections'),
          ),
          (
            'Security & sign-in',
            LucideIcons.lockKeyhole,
            () => _security(context, ref),
          ),
          (
            'Notifications',
            LucideIcons.bell,
            () => showDetail(
              context,
              'Notifications',
              const _NotificationSettings(),
            ),
          ),
          (
            'About Ultron',
            LucideIcons.info,
            () => showUltronAbout(context),
          ),
        ])
          ListTile(
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 3,
              vertical: 3,
            ),
            leading: Icon(destination.$2, size: 20),
            title: Text(destination.$1, style: const TextStyle(fontSize: 14)),
            trailing: const Icon(LucideIcons.chevronRight, size: 16),
            onTap: destination.$3,
          ),
        ListTile(
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 3,
            vertical: 3,
          ),
          leading: const Icon(LucideIcons.palette, size: 20),
          title: const Text('Appearance', style: TextStyle(fontSize: 14)),
          trailing: DropdownButton<ThemeMode>(
            value: ref.watch(themeModeProvider),
            underline: const SizedBox.shrink(),
            items: const [
              DropdownMenuItem(value: ThemeMode.system, child: Text('System')),
              DropdownMenuItem(value: ThemeMode.light, child: Text('Light')),
              DropdownMenuItem(value: ThemeMode.dark, child: Text('Dark')),
            ],
            onChanged: (value) {
              if (value != null) {
                ref.read(themeModeProvider.notifier).set(value);
              }
            },
          ),
        ),
        const SizedBox(height: 25),
        OutlinedButton.icon(
          key: const Key('sign-out'),
          onPressed: () => ref.read(authProvider.notifier).signOut(),
          icon: const Icon(LucideIcons.logOut, size: 18),
          label: const Text('Sign out'),
        ),
        const SizedBox(height: 18),
        Text(
          'Ultron · Frontend ${AppInfo.version}',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    ),
  );

  void _security(BuildContext context, WidgetRef ref) => showDetail(
    context,
    'Security & sign-in',
    Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'This frontend uses a demo account and an in-memory session. A live authentication service, device management and secure token storage are not connected.',
        ),
        const SizedBox(height: 20),
        OutlinedButton(
          onPressed: () {
            Navigator.pop(context);
            ref.read(authProvider.notifier).signOut();
          },
          child: const Text('Preview session expiry'),
        ),
      ],
    ),
  );
}

class ConnectionsScreen extends StatelessWidget {
  const ConnectionsScreen({super.key});
  @override
  Widget build(BuildContext context) => DataGate(
    builder: (data) => PageBody(
      maxWidth: 900,
      children: [
        const PageHeading(
          'Connections',
          subtitle: 'Account health without exposing credentials.',
        ),
        Card(
          child: Column(
            children: [
              for (final connection in data.connections)
                _ConnectionRow(connection: connection),
            ],
          ),
        ),
        const SizedBox(height: 22),
        const NotePanel(
          'Connection states are a sample snapshot. Reconnection will use the supported owner login flow.',
        ),
      ],
    ),
  );
}

class _ConnectionRow extends StatelessWidget {
  const _ConnectionRow({required this.connection});
  final PortalConnection connection;
  @override
  Widget build(BuildContext context) => InkWell(
    onTap: () => showConnectionDetail(context, connection),
    borderRadius: BorderRadius.circular(16),
    child: Padding(
      padding: const EdgeInsets.all(15),
      child: Row(
        children: [
          PortalIcon(
            connection.name,
            size: 33,
            icon: connection.name == 'Google Drive' ? LucideIcons.folder : null,
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  connection.name,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (MediaQuery.textScalerOf(context).scale(1) > 1.3) ...[
                  const SizedBox(height: 8),
                  StatusBadge(
                    status: connection.available
                        ? RunStatus.completed
                        : RunStatus.blocked,
                  ),
                ],
              ],
            ),
          ),
          if (MediaQuery.textScalerOf(context).scale(1) <= 1.3) ...[
            const SizedBox(width: 8),
            StatusBadge(
              status: connection.available
                  ? RunStatus.completed
                  : RunStatus.blocked,
            ),
          ],
          const SizedBox(width: 6),
          const Icon(LucideIcons.chevronRight, size: 15),
        ],
      ),
    ),
  );
}

class _NotificationSettings extends StatefulWidget {
  const _NotificationSettings();
  @override
  State<_NotificationSettings> createState() => _NotificationSettingsState();
}

class _NotificationSettingsState extends State<_NotificationSettings> {
  bool _approvals = true;
  bool _failures = true;
  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      SwitchListTile.adaptive(
        contentPadding: EdgeInsets.zero,
        title: const Text('Approval requests'),
        value: _approvals,
        onChanged: (value) => setState(() => _approvals = value),
      ),
      SwitchListTile.adaptive(
        contentPadding: EdgeInsets.zero,
        title: const Text('Run failures'),
        value: _failures,
        onChanged: (value) => setState(() => _failures = value),
      ),
      const SizedBox(height: 12),
      const NotePanel(
        'These are local preview preferences. Push notifications are not connected.',
      ),
    ],
  );
}

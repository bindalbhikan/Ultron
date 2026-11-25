import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:material_ui/material_ui.dart';

import '../app_info.dart';
import '../domain/access.dart';
import '../state/providers.dart';
import 'components.dart';
import 'sms_sheet_card.dart';
import 'update_notice.dart';

void showUltronAbout(BuildContext context) => showAboutDialog(
  context: context,
  applicationName: AppInfo.name,
  applicationVersion: AppInfo.version,
  applicationIcon: const BrandMark(size: 40),
  children: const [
    Text('Developed by ${AppInfo.developer}'),
    SizedBox(height: 12),
    Text(
      'Users and access, the agent\'s model and memory, and SMS to the sheet.',
    ),
    SizedBox(height: 8),
    Text('Flutter ${AppInfo.flutterVersion} · Dart ${AppInfo.dartVersion}'),
  ],
);

/// Profile, and the pages a signed-in person sees without access: waiting for approval, disabled, or
/// a feature their role does not include.
class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key, this.pending = false, this.denied = false});
  final bool pending, denied;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(authProvider);
    final user = session.user;
    final theme = Theme.of(context);
    Future<void> signOut() async {
      await ref.read(authProvider.notifier).signOut();
      if (context.mounted) context.go('/login');
    }

    final content = PageBody(
      maxWidth: 720,
      children: [
        if (pending) ...[
          const BrandMark(size: 32, wordmark: true),
          const SizedBox(height: 32),
        ],
        PageHeading(
          denied
              ? 'Not in your role'
              : pending
              ? (user?.status == 'disabled'
                    ? 'Account disabled'
                    : 'Waiting for approval')
              : 'Profile',
          subtitle: pending
              ? 'An administrator decides what your account can open.'
              : denied
              ? 'Ask an administrator to add this to your role.'
              : null,
        ),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  user?.name ?? 'Account',
                  style: theme.textTheme.titleLarge,
                ),
                const SizedBox(height: 4),
                Text(
                  '@${user?.username ?? ''}',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    StatusPill(user?.roleName ?? 'No role'),
                    StatusPill(
                      user?.status ?? 'unknown',
                      tone: switch (user?.status) {
                        'active' => Tone.good,
                        'pending' => Tone.warn,
                        _ => Tone.bad,
                      },
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        if (pending)
          const NotePanel(
            'Your account exists but opens nothing yet. Once an administrator approves it, tap '
            '"Check again" or sign in again.',
          ),
        if (!pending && !denied) ...[
          if (user?.permissions.contains('agent.tools.read') ?? false)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(LucideIcons.brain),
              title: const Text('AI providers and models'),
              subtitle: const Text(
                'Choose a model, add API keys and set fallbacks',
              ),
              onTap: () => context.go('/app/control'),
            ),
          const UpdateNotice(full: true),
          const SmsSheetCard(),
          const SectionHeading('Appearance'),
          SegmentedButton<ThemeMode>(
            segments: const [
              ButtonSegment(
                value: ThemeMode.light,
                label: Text('Light'),
                icon: Icon(LucideIcons.sun, size: 16),
              ),
              ButtonSegment(
                value: ThemeMode.dark,
                label: Text('Dark'),
                icon: Icon(LucideIcons.moon, size: 16),
              ),
              ButtonSegment(
                value: ThemeMode.system,
                label: Text('Phone'),
                icon: Icon(LucideIcons.smartphone, size: 16),
              ),
            ],
            selected: {ref.watch(themeModeProvider)},
            onSelectionChanged: (v) =>
                ref.read(themeModeProvider.notifier).set(v.first),
          ),
          const SectionHeading('What your role allows'),
          Card(
            child: Column(
              children: [
                for (final p in user?.permissions ?? const <String>[])
                  ListTile(
                    dense: true,
                    leading: const Icon(LucideIcons.check, size: 18),
                    title: Text(accessPermissions[p] ?? p),
                  ),
              ],
            ),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(LucideIcons.info),
            title: const Text('About ULTRON'),
            onTap: () => showUltronAbout(context),
          ),
        ],
        if (session.error != null) ...[
          const SizedBox(height: 12),
          NotePanel(session.error!, warning: true),
        ],
        const SizedBox(height: 20),
        OutlinedButton.icon(
          onPressed: session.busy
              ? null
              : () => ref.read(authProvider.notifier).refreshAccess(),
          icon: const Icon(LucideIcons.refreshCw, size: 18),
          label: Text(session.busy ? 'Checking…' : 'Check again'),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          key: const Key('sign-out'),
          onPressed: signOut,
          icon: const Icon(LucideIcons.logOut, size: 18),
          label: const Text('Sign out'),
        ),
        const SizedBox(height: 24),
        Text(
          'Developed by ${AppInfo.developer}',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
    return pending ? Scaffold(body: SafeArea(child: content)) : content;
  }
}
